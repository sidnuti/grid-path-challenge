"""L2′'s own LLM stack: the same layers as `harness.llm.build_llm_stack` (provider → faults → Meter →
ReplayClient), with one addition the planner needs and `harness/` does not offer: control over a
reasoning model's thinking budget through OpenRouter's `reasoning` request field.

`L2P_MODEL` defaults to qwen/qwen3.7-flash. `L2P_REASONING` = on (default) | off | low | medium | high | default.
(A live check on z-ai/glm-5.3-flashx with thinking at its default used ~19k output tokens and ~2 minutes per
plan; at effort=low, ~2.8k and 18 s. That endpoint refuses `enabled: false`.)

`PricedMeter` prices calls from `PRICES` (OpenRouter list prices, checked 2026-10-04), because the
harness Meter's table has no row for these models and would fall back to $3 / $15 per million tokens.
"""

from __future__ import annotations

import os
import time

from harness.config import Params
from harness.llm import _load_dotenv_once
from harness.llm.client import Usage
from harness.llm.faults import FaultInjectingClient
from harness.llm.meter import Meter
from harness.llm.providers import _JSON_ONLY, _REPAIR, OpenRouterClient, _extract_json, build_provider
from harness.llm.replay import ReplayClient

import json

DEFAULT_MODEL = "qwen/qwen3.7-flash"
PRICES = {"qwen3.7-flash": {"in": 0.03, "out": 0.13}, "qwen3.7-plus": {"in": 0.32, "out": 1.28},
          "glm-5.3-flash": {"in": 0.37, "out": 1.25}}


def price_of(model: str) -> dict:
    for k, p in PRICES.items():
        if k in (model or ""):
            return p
    from harness.llm.meter import price_for
    return price_for(model or "")


class PricedMeter(Meter):
    def complete_json(self, system: str, user: str, schema: dict, timeout: float, **kwargs):
        from harness.llm.meter import BudgetExceeded
        if self.inner is None:
            raise RuntimeError("PricedMeter has no inner LLMClient")
        parsed, u = self.inner.complete_json(system, user, schema, timeout, **kwargs)
        p = price_of(self.model)
        u.cost_usd = (u.tokens_in * p["in"] + u.tokens_out * p["out"]) / 1e6
        self.usage = self.usage + u
        self.run_usage = self.run_usage + u
        if self.run_usage.cost_usd > self.max_usd_per_run:
            raise BudgetExceeded(self.run_usage.cost_usd, self.max_usd_per_run)
        return parsed, u


class OpenRouterReasoningClient(OpenRouterClient):
    def __init__(self, model: str, reasoning: str = "on", max_tokens: int = 12000):
        super().__init__(model=model)
        self.reasoning, self.max_tokens = reasoning, max_tokens

    def _extra(self) -> dict:
        if self.reasoning == "default":
            return {}
        if self.reasoning == "on":
            return {"reasoning": {"enabled": True}}
        if self.reasoning == "off":
            return {"reasoning": {"enabled": False}}
        return {"reasoning": {"effort": self.reasoning}}

    def complete_json(self, system: str, user: str, schema: dict, timeout: float, **_ignored) -> tuple[dict, Usage]:
        t0 = time.monotonic()
        messages = [{"role": "system", "content": system + "\n\n" + _JSON_ONLY.format(schema=json.dumps(schema))},
                    {"role": "user", "content": user}]
        usage = Usage()
        for _ in range(2):
            resp = self._client.chat.completions.create(model=self.model, messages=messages, timeout=timeout,
                                                        max_tokens=self.max_tokens, extra_body=self._extra())
            u = getattr(resp, "usage", None)
            if u is not None:
                usage.calls += 1
                usage.tokens_in += getattr(u, "prompt_tokens", 0) or 0
                usage.tokens_out += getattr(u, "completion_tokens", 0) or 0
            text = resp.choices[0].message.content or ""
            try:
                parsed = _extract_json(text)
                usage.wall_clock_s += time.monotonic() - t0
                return parsed, usage
            except (json.JSONDecodeError, ValueError) as e:
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": _REPAIR.format(error=str(e))})
        usage.wall_clock_s += time.monotonic() - t0
        raise ValueError(f"{self.model}: no valid JSON after one repair retry")


def build_l2p_stack(params: Params):
    """Returns (client_or_None, mode), like `harness.llm.build_llm_stack`."""
    _load_dotenv_once()
    mode = os.environ.get("LLM_MODE", "off")
    if mode == "off":
        return None, mode
    provider_name = os.environ.get("LLM_PROVIDER", "openrouter")
    model = os.environ.get("L2P_MODEL") or DEFAULT_MODEL
    if provider_name == "openrouter":
        provider = OpenRouterReasoningClient(model, os.environ.get("L2P_REASONING", "on"))
    else:
        provider = build_provider(provider_name, model)
    if provider is None:
        return None, mode
    faulted = FaultInjectingClient(provider, os.environ.get("FAULT_INJECT", ""))
    metered = PricedMeter(faulted, model or "", params.llm_max_usd_per_run)
    cache_dir = os.environ.get("LLM_CACHE_DIR", "llm_cache")
    return ReplayClient(metered, cache_dir, mode), mode
