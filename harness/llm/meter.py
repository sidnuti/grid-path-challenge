"""Cost/token/call/wall-clock metering, with a per-run budget (`LLM_MAX_USD_PER_RUN` /
`params.llm_max_usd_per_run`). `Meter` wraps any `LLMClient` and is itself one, so a leaf never
needs to know metering exists.

Tracks two totals: `usage` (lifetime, since this `Meter` was built — a policy instance builds one
`Meter` and reuses it across every run in a `simulate()` call, so this is "cost so far this
simulation", not "cost this run") and `run_usage` (since the last `reset_run()` call). Budget is
enforced against `run_usage`, matching the env var's own name (`LLM_MAX_USD_PER_RUN`) — **fixed
2026-10-02** (an independent review session caught this): before the fix, both the budget check
and `usage_of()` read the same ever-growing `usage` total, so a multi-run `simulate()` call's
*per-run* budget was silently actually a *per-simulation* budget (run 1 could spend the whole
budget and every later run would immediately hit `BudgetExceeded`, or vice versa depending on
order). `harness/policy.py` calls `reset_run_budget(llm)` at the start of every `recommend()`.
`usage_of()` still reports the lifetime total — that one's the right number for "what did this
whole evaluation cost", which is what `harness_eval/run_matrix.py` and the trace's `usage` field
both actually want.

Price table is approximate (public list-price pages change faster than this file will) and is a
fallback only: pass `price_usd_per_mtok={"in":..., "out":...}` to override per deployment without
touching code. Keyed by a substring match on the model id so `anthropic/claude-sonnet-5` and
`claude-sonnet-5` both hit the same row.
"""

from __future__ import annotations

from .client import LLMClient, Usage

DEFAULT_PRICE_USD_PER_MTOK = {
    "claude-opus": {"in": 15.0, "out": 75.0},
    "claude-sonnet": {"in": 3.0, "out": 15.0},
    "claude-haiku": {"in": 1.0, "out": 5.0},
    "gpt-5": {"in": 5.0, "out": 15.0},
    "gpt-4o-mini": {"in": 0.15, "out": 0.6},
    "gpt-4o": {"in": 2.5, "out": 10.0},
    # Added 2026-10-03 after the first real LLM-arm run used the $3/$15 fallback (Claude-Sonnet
    # pricing) for a model that costs ~8-12x less — OpenRouter's published rate for the
    # z-ai/glm-5.3-flashx model configured in .env (per openrouter.ai/z-ai/glm-5.3-flashx).
    "glm-5.3-flashx": {"in": 0.37, "out": 1.25},
    "glm-5.3-flash": {"in": 0.37, "out": 1.25},  # covers the non-X variant too, same published rate
}
FALLBACK_PRICE = {"in": 3.0, "out": 15.0}


class BudgetExceeded(RuntimeError):
    def __init__(self, spent_usd: float, max_usd: float):
        super().__init__(f"LLM budget exceeded: ${spent_usd:.4f} > ${max_usd:.4f} for this run")
        self.spent_usd = spent_usd
        self.max_usd = max_usd


def price_for(model: str) -> dict:
    for key, price in DEFAULT_PRICE_USD_PER_MTOK.items():
        if key in model:
            return price
    return FALLBACK_PRICE


def _usage_dict(u) -> dict:
    return {"calls": u.calls, "tokens_in": u.tokens_in, "tokens_out": u.tokens_out,
           "cost_usd": round(u.cost_usd, 4), "wall_clock_s": round(u.wall_clock_s, 2)}


_ZERO_USAGE = {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "wall_clock_s": 0.0}


def _find_meter_attr(llm, attr: str) -> dict:
    node = llm
    for _ in range(5):
        if node is None:
            break
        if hasattr(node, attr):
            return _usage_dict(getattr(node, attr))
        node = getattr(node, "inner", None)
    return dict(_ZERO_USAGE)


def usage_of(llm) -> dict:
    """Walks an `llm` client's `.inner` chain (as `ReplayClient` -> `Meter` ->
    `FaultInjectingClient` -> provider is built, see `harness/llm/__init__.py::build_llm_stack`)
    looking for the first `.usage` attribute, i.e. the `Meter` in the stack: the **lifetime**
    total since that `Meter` was built (a policy instance builds one, reused across every run in
    a `simulate()` call). Returns all-zero usage for `llm=None` or a stack with no `Meter` (e.g. a
    bare mock in a test). For this run's usage alone, see `run_usage_of`."""
    return _find_meter_attr(llm, "usage")


def run_usage_of(llm) -> dict:
    """Same chain-walk as `usage_of`, but reads `.run_usage` — the total **since the last
    `reset_run()`** (`harness/policy.py` calls `reset_run_budget` at the start of every
    `recommend()`), i.e. this run's own usage. This is what `harness/trace/schema.py` puts in
    `RunTrace.usage` — added 2026-10-03 alongside `Meter.run_usage` itself; before that, a trace
    reader had to diff two consecutive JSONL lines to get a per-run number from the lifetime
    total `usage_of` returns, which this makes unnecessary."""
    return _find_meter_attr(llm, "run_usage")


def reset_run_budget(llm) -> None:
    """Walks the same `.inner` chain as `usage_of` and calls `reset_run()` on the first `Meter`
    found, if any. `harness/policy.py` calls this at the start of every `recommend()` so
    `LLM_MAX_USD_PER_RUN` is enforced per run, not per policy-instance-lifetime."""
    node = llm
    for _ in range(5):
        if node is None:
            return
        if hasattr(node, "reset_run"):
            node.reset_run()
            return
        node = getattr(node, "inner", None)


class Meter:
    def __init__(self, inner: LLMClient | None, model: str, max_usd_per_run: float):
        self.inner = inner
        self.model = model
        self.max_usd_per_run = max_usd_per_run
        self.usage = Usage()        # lifetime, since this Meter was built
        self.run_usage = Usage()    # since the last reset_run()

    def reset_run(self) -> None:
        self.run_usage = Usage()

    def complete_json(self, system: str, user: str, schema: dict, timeout: float, **kwargs) -> tuple[dict, Usage]:
        if self.inner is None:
            raise RuntimeError("Meter has no inner LLMClient (provider is 'none')")
        parsed, call_usage = self.inner.complete_json(system, user, schema, timeout, **kwargs)
        price = price_for(self.model)
        call_usage.cost_usd = (call_usage.tokens_in * price["in"] + call_usage.tokens_out * price["out"]) / 1e6
        self.usage = self.usage + call_usage
        self.run_usage = self.run_usage + call_usage
        if self.run_usage.cost_usd > self.max_usd_per_run:
            raise BudgetExceeded(self.run_usage.cost_usd, self.max_usd_per_run)
        return parsed, call_usage
