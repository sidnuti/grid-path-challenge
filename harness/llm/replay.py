"""Deterministic replay cache. `LLM_MODE`:

    off     — never reach this class; `harness/leaves/run.py` returns the leaf default directly.
    record  — call the inner client, cache the result, return it.
    replay  — look up the cache; a miss is a hard error (reproducibility would otherwise silently
              fall through to a live call and stop being reproducible).
    live    — always call the inner client, cache nothing, read nothing.

Cache key = sha256(leaf name, prompt_ver, model, rendered system+user text, schema_ver, replicate
index). One file per key under `LLM_CACHE_DIR` (default `llm_cache/`), so a committed replay set
is just a directory of small JSON files — reviewable, diffable, and exactly what a second-run
reproduction check (`LLM_MODE=replay make score ...`) depends on.

**Bug fixed 2026-10-02** (found by an independent review session reading this code, not by a
test): the cache key originally didn't include `model`, so switching `LLM_MODEL` while reusing a
cache directory could silently replay a different model's cached response as if it were the
configured one. `model` is now part of the key. A cache recorded before this fix has a different
key and will simply miss (not silently misattribute), which is the safe failure mode.

Also fixed in the same pass: a cache hit (either `replay` mode, or `record` mode re-hitting an
already-cached key) used to return the cached `Usage` straight to the caller without ever
updating the wrapped `Meter`'s running total — so `Meter.usage` (what
`harness.llm.meter.usage_of` and the trace both report) undercounted cost for anything that got
served from cache, and `harness_eval/run_matrix.py`'s `replay`-mode cost columns were simply
wrong. A cache hit now credits the cached `Usage` to the inner `Meter` (if the wrapped client is
one — duck-typed via `hasattr(..., "usage")`) exactly as a live call would have, so the `Meter`'s
accumulated total reflects every response actually served, not just the ones that triggered a
network call.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from .client import LLMClient, Usage

MODES = ("off", "record", "replay", "live")


def cache_key(leaf: str, prompt_ver: str, model: str, system: str, user: str, schema_ver: str,
             replicate: int = 0) -> str:
    h = hashlib.sha256()
    for part in (leaf, prompt_ver, model, system, user, schema_ver, str(replicate)):
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


class ReplayClient:
    def __init__(self, inner: LLMClient | None, cache_dir: str | Path, mode: str):
        if mode not in MODES:
            raise ValueError(f"LLM_MODE must be one of {MODES}, got {mode!r}")
        self.inner = inner
        self.cache_dir = Path(cache_dir)
        self.mode = mode

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _credit_cached_usage(self, usage: Usage) -> None:
        """Mirrors what `Meter.complete_json` would have added to its running total, for a
        response served from cache instead of a live call — without this, `Meter.usage` only
        counts cache *misses*, which is not "how much this policy actually cost to serve"."""
        if hasattr(self.inner, "usage"):
            self.inner.usage = self.inner.usage + usage
        if hasattr(self.inner, "run_usage"):
            self.inner.run_usage = self.inner.run_usage + usage

    def complete_json(self, system: str, user: str, schema: dict, timeout: float, *, leaf: str = "",
                      prompt_ver: str = "0", schema_ver: str = "0", replicate: int = 0) -> tuple[dict, Usage]:
        model = getattr(self.inner, "model", "")
        key = cache_key(leaf, prompt_ver, model, system, user, schema_ver, replicate)
        path = self._path(key)

        if self.mode == "replay":
            if not path.exists():
                raise FileNotFoundError(f"LLM_MODE=replay cache miss for leaf={leaf!r} key={key}")
            cached = json.loads(path.read_text())
            usage = Usage(**cached["usage"])
            self._credit_cached_usage(usage)
            return cached["response"], usage

        if self.mode == "record" and path.exists():
            cached = json.loads(path.read_text())
            usage = Usage(**cached["usage"])
            self._credit_cached_usage(usage)
            return cached["response"], usage

        if self.inner is None:
            raise RuntimeError(f"LLM_MODE={self.mode} needs a provider, but none is configured")
        parsed, usage = self.inner.complete_json(system, user, schema, timeout)

        if self.mode == "record":
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"leaf": leaf, "prompt_ver": prompt_ver, "model": model,
                                        "schema_ver": schema_ver, "replicate": replicate, "response": parsed,
                                        "usage": asdict(usage)}, indent=2))
        return parsed, usage
