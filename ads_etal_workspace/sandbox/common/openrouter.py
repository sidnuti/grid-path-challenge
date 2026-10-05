"""OpenRouter access for the sandbox: record/replay cache + programme ledger, at the HTTP layer.

One `httpx` transport (`CachingTransport`) sits under both clients we need:
  * Chimera  -> langchain `ChatOpenAI(http_client=...)`
  * MoHOLLM  -> `openai.OpenAI(http_client=...)`
so there is exactly one place where money can be spent and one place where it is counted.

`SANDBOX_LLM_MODE`:
    replay (default) — cache only; a miss is a hard error (never silently falls through to a paid call)
    record           — cache hit -> serve free; miss -> ledger check, live call, cache, ledger
    live             — always call, cache nothing (still ledgered and capped)

Cache key = sha256(salt, canonical request JSON) + "." + n, where n counts how many times that exact
request has been seen in this process. Identical prompts at temperature > 0 (e.g. the same prompt in
two weeks of a simulation) therefore get their own recorded sample, and replay serves them in order.
`salt` is the run tag (model, seed, ...), so different seeds never share samples.

Prices are true OpenRouter per-token rates (checked 2026-10-05 against /api/v1/models). An unknown
model is an error: there is deliberately NO fallback price (the $3/$15 fallback in
`harness/llm/meter.py` silently mis-priced cheap models).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
from pathlib import Path

import httpx

from . import ledger

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://openrouter.ai/api/v1"
CACHE_ROOT = Path(os.environ.get("SANDBOX_CACHE_DIR", ROOT / "cache"))
GPC_ENV = ROOT.parent / "grid-path-challenge" / ".env"

# USD per 1M tokens (prompt, completion).
MODEL = "minimax/minimax-m3"   # user decision 2026-10-05: the model for BOTH replications (reasoning model)
PRICES = {
    MODEL: (0.30, 1.20),       # reasoning tokens are billed as completion tokens
    "openai/gpt-4o": (2.50, 10.00),
    "qwen/qwen3.7-flash": (0.03, 0.13),
    # google/gemini-2.0-flash-001 (the MoHOLLM paper's model) is no longer listed on OpenRouter.
    # Stand-in: same $0.10/$0.40 price tier, non-reasoning by default.
    "google/gemini-2.5-flash-lite": (0.10, 0.40),
}
PAPER_MODEL_ALIASES = {  # what upstream code asks for -> what we send (everything runs on MODEL)
    "gpt-4o": MODEL, "openai/gpt-4o": MODEL,
    "gemini-2.0-flash": MODEL, "gemini-2.0-flash-001": MODEL, "google/gemini-2.0-flash-001": MODEL,
}


def resolve_model(model: str) -> str:
    return PAPER_MODEL_ALIASES.get(model, model)


def price_of(model: str) -> tuple[float, float]:
    try:
        return PRICES[model]
    except KeyError:
        raise KeyError(f"no price for model {model!r}; add it to common/openrouter.py::PRICES "
                       f"(no fallback price by design)") from None


def cost_of(model: str, tokens_in: int, tokens_out: int) -> float:
    pin, pout = price_of(model)
    return (tokens_in * pin + tokens_out * pout) / 1e6


def reasoning_setting() -> dict | None:
    """`SANDBOX_REASONING`: unset/`default` (provider default = on for minimax-m3) | `low` | `medium` | `high` | `off`.
    Injected into every chat request by the transport, so all arms of a replication share one setting and the setting is part
    of the cache key (recordings made under different settings never mix)."""
    r = os.environ.get("SANDBOX_REASONING", "default")
    if r == "default":
        return None
    if r == "off":
        return {"enabled": False}
    if r in ("low", "medium", "high"):
        return {"effort": r}
    raise ValueError(f"SANDBOX_REASONING must be default|low|medium|high|off, got {r!r}")


def mode() -> str:
    m = os.environ.get("SANDBOX_LLM_MODE", "replay")
    if m not in ("replay", "record", "live"):
        raise ValueError(f"SANDBOX_LLM_MODE must be replay|record|live, got {m!r}")
    return m


def api_key() -> str:
    """OPENROUTER_API_KEY from the environment, else from the GPC .env. Never printed or logged."""
    k = os.environ.get("OPENROUTER_API_KEY")
    if not k and GPC_ENV.exists():
        m = re.search(r"^OPENROUTER_API_KEY=(.+)$", GPC_ENV.read_text(), re.M)
        k = m.group(1).strip().strip("'\"") if m else None
    if not k:
        raise RuntimeError("OPENROUTER_API_KEY not set (environment or grid-path-challenge/.env)")
    return k


class ReplayMiss(ledger.SandboxHalt):
    pass


def _canonical(body: dict) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _call_with_deadline(fn, seconds: float):
    """Run fn() with a hard wall-clock deadline. httpx's timeouts are per-read, and OpenRouter keeps a connection alive while an
    upstream provider stalls, so a hung request can block forever (seen: runs silent for hours, blocked in a TLS read). On expiry the
    worker thread is abandoned (daemon) and httpx.ReadTimeout is raised, which the OpenAI SDK retries."""
    box = {}

    def run():
        try:
            box["v"] = fn()
        except BaseException as e:            # noqa: BLE001 - re-raised in the caller
            box["e"] = e
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise httpx.ReadTimeout(f"no complete response within {seconds:.0f}s wall-clock")
    if "e" in box:
        raise box["e"]
    return box["v"]


class CachingTransport(httpx.BaseTransport):
    """Intercepts POST .../chat/completions. Everything else passes through (live) or errors (replay)."""

    def __init__(self, item: str, salt: str = "", cache_dir: Path | None = None, mode_: str | None = None,
                 max_default_out: int = 4096):
        if item not in ledger.CAPS:
            raise ValueError(f"unknown ledger item {item!r}")
        self.item, self.salt = item, salt
        self.cache_dir = Path(cache_dir) if cache_dir else CACHE_ROOT / item
        self.mode = mode_ or mode()
        self.max_default_out = max_default_out
        self._seen: dict[str, int] = {}
        self.max_live_repeats = int(os.environ.get("SANDBOX_MAX_LIVE_REPEATS", "14"))   # retry-storm guard
        self._lock = threading.Lock()          # MoHOLLM calls the LLM from a thread pool
        self._inner = httpx.HTTPTransport()

    # -- helpers ---------------------------------------------------------------------------------
    def _key(self, body: dict) -> str:
        base = hashlib.sha256((self.salt + "\0" + _canonical(body)).encode()).hexdigest()
        with self._lock:
            n = self._seen.get(base, 0)
            self._seen[base] = n + 1
        return f"{base}.{n}"

    @staticmethod
    def _usage(resp_json: dict) -> tuple[int, int, float | None]:
        u = resp_json.get("usage") or {}
        return int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0)), u.get("cost")

    def _projected(self, body: dict, model: str) -> float:
        """Worst case for the pre-call cap check: prompt chars/3 tokens + the full max_tokens budget."""
        tin = len(_canonical(body.get("messages", []))) // 3 + 50
        tout = int(body.get("max_tokens") or body.get("max_completion_tokens") or self.max_default_out)
        return cost_of(model, tin, tout)

    # -- transport -------------------------------------------------------------------------------
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.method != "POST" or not request.url.path.endswith("/chat/completions"):
            if self.mode == "replay":
                raise ReplayMiss(f"replay mode: non-chat request {request.method} {request.url.path}")
            return self._inner.handle_request(request)

        body = json.loads(request.content)
        rs = reasoning_setting()
        if rs is not None:
            body["reasoning"] = rs
            request = httpx.Request("POST", request.url, headers={k: v for k, v in request.headers.items() if k.lower() != "content-length"},
                                    content=json.dumps(body).encode())
        if body.get("stream"):
            raise ledger.SandboxHalt("streaming is not supported by the sandbox transport (set disable_streaming)")
        model = body["model"]
        try:
            price_of(model)                                 # fail early on unpriced models
        except KeyError as e:
            raise ledger.SandboxHalt(str(e)) from None
        key = self._key(body)
        path = self.cache_dir / f"{key}.json"

        if self.mode in ("replay", "record") and path.exists():
            cached = json.loads(path.read_text())
            tin, tout, _ = self._usage(cached["response"])
            ledger.record(self.item, model, tin, tout, cost_of(model, tin, tout), cached=True, key=key, note=os.environ.get("SANDBOX_RUN_TAG", ""))
            return self._respond(request, cached["response"])
        if self.mode == "replay":
            if os.environ.get("SANDBOX_DEBUG_MISS"):          # dump the request that missed, for diffing against the cache
                Path(os.environ["SANDBOX_DEBUG_MISS"]).write_text(json.dumps({"key": key, "body": body}))
            raise ReplayMiss(f"replay cache miss ({self.item}, model={model}, key={key[:12]}); "
                             f"record it with SANDBOX_LLM_MODE=record")

        n = int(key.rsplit(".", 1)[1])
        if n >= self.max_live_repeats:
            raise ledger.SandboxHalt(f"retry storm: the identical request has been sent {n} times ({self.item}, key={key[:12]}). "
                                     f"Upstream retries failing prompts forever (MoHOLLM surrogate `while True`); stopping instead of paying again.")
        mt = body.get("max_tokens")
        if mt and n >= 4:
            # A prompt that keeps coming back truncated (finish_reason=length, empty answer) is failing for lack of output budget,
            # not by bad luck: give each further attempt more room (x2 from the 5th, x3 from the 9th, capped at 32k). The cache key was
            # computed from the ORIGINAL body above, so replay finds the same slots and stays deterministic.
            body["max_tokens"] = min(32000, mt * (1 + n // 4))
        ledger.check(self.item, self._projected(body, model))   # BEFORE the call
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ("authorization", "content-length")}
        live = httpx.Request("POST", request.url, headers={**headers, "Authorization": f"Bearer {api_key()}"},
                             content=json.dumps(body).encode())
        deadline = float(os.environ.get("SANDBOX_REQUEST_DEADLINE", 0)) or 120 + (body.get("max_tokens") or self.max_default_out) / 40
        resp, raw = _call_with_deadline(lambda: (lambda r: (r, r.read()))(self._inner.handle_request(live)), deadline)
        if resp.status_code != 200:
            with self._lock:                                   # a failed attempt is not a sample: release its slot so SDK retries
                self._seen[key.rsplit(".", 1)[0]] -= 1         # neither shift replay order nor trip the retry-storm guard
            return httpx.Response(resp.status_code, headers={"content-type": "application/json"}, content=raw,
                                  request=request)
        data = json.loads(raw)
        tin, tout, provider_cost = self._usage(data)
        ledger.record(self.item, model, tin, tout, cost_of(model, tin, tout), cached=False, key=key,
                      note=os.environ.get("SANDBOX_RUN_TAG", ""), provider_cost_usd=provider_cost)
        if self.mode == "record":
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"model": model, "salt": self.salt, "request": body, "response": data}, indent=1))
        return self._respond(request, data)

    @staticmethod
    def _respond(request: httpx.Request, data: dict) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/json"}, content=json.dumps(data).encode(),
                              request=request)


def http_client(item: str, salt: str = "", **kw) -> httpx.Client:
    return httpx.Client(transport=CachingTransport(item, salt, **kw), timeout=300.0)


def openai_client(item: str, salt: str = "", **kw):
    """`openai.OpenAI` pointed at OpenRouter through the caching transport (no SDK retries)."""
    from openai import OpenAI
    key = api_key() if mode() != "replay" else "replay-no-key"
    return OpenAI(api_key=key, base_url=BASE_URL, http_client=http_client(item, salt, **kw), max_retries=3)


def chat(item: str, model: str, prompt: str, *, max_tokens: int = 16, salt: str = "", temperature: float = 0.0):
    """One-shot completion; returns (text, tokens_in, tokens_out). Used by the Gate-P0 ping script."""
    model = resolve_model(model)
    c = openai_client(item, salt)
    r = c.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}],
                                  max_tokens=max_tokens, temperature=temperature)
    return r.choices[0].message.content, r.usage.prompt_tokens, r.usage.completion_tokens
