"""Deterministic fault injection for the fail-soft tests (`FAULT_INJECT` env var). Wraps any
`LLMClient`; with `FAULT_INJECT` unset or `""` it is a pure passthrough. Each mode exercises a
different point in the leaf -> validate -> default fail-soft chain (`harness/leaves/run.py`):

    timeout       raises TimeoutError — the leaf should catch it and return its default.
    exception     raises a generic RuntimeError — same, via the broad except.
    malformed     returns a response with none of the schema's fields — pydantic validation
                  fails, the leaf returns its default.
    out_of_range  returns a response with every numeric/string/bool field present but pushed to
                  an extreme value — `validate_and_clip` should clip it, not crash or default.
    budget        raises `harness.llm.meter.BudgetExceeded` without calling the inner client —
                  exercises the per-run budget fail-soft path independent of whether the budget
                  would actually be hit.
"""

from __future__ import annotations

from .client import LLMClient, Usage
from .meter import BudgetExceeded

MODES = ("", "timeout", "exception", "malformed", "out_of_range", "budget")


def _out_of_range_response(schema: dict) -> dict:
    out = {}
    for name, prop in (schema.get("properties") or {}).items():
        t = prop.get("type")
        if t in ("number", "integer"):
            out[name] = 1e12
        elif t == "string":
            out[name] = "x" * 10_000
        elif t == "boolean":
            out[name] = True
        elif t == "array":
            out[name] = []
    return out


class FaultInjectingClient:
    def __init__(self, inner: LLMClient | None, mode: str = ""):
        if mode not in MODES:
            raise ValueError(f"FAULT_INJECT must be one of {MODES}, got {mode!r}")
        self.inner = inner
        self.mode = mode

    def complete_json(self, system: str, user: str, schema: dict, timeout: float, **kwargs) -> tuple[dict, Usage]:
        if self.mode == "timeout":
            raise TimeoutError("FAULT_INJECT=timeout")
        if self.mode == "exception":
            raise RuntimeError("FAULT_INJECT=exception")
        if self.mode == "budget":
            raise BudgetExceeded(spent_usd=999.0, max_usd=0.01)
        if self.mode == "malformed":
            return {"_fault": "malformed"}, Usage(calls=1)
        if self.mode == "out_of_range":
            return _out_of_range_response(schema), Usage(calls=1)
        if self.inner is None:
            raise RuntimeError("no provider configured and no fault injected")
        return self.inner.complete_json(system, user, schema, timeout, **kwargs)
