"""`leaf()`: the one call site every L1-L6 integration goes through. Narrows `ctx` to a rendered
prompt, calls the LLM client, validates+clips the response against the leaf's schema, and returns
`default` on *any* failure — a bad provider response should never propagate past this function.
`harness/policy.py`'s own fail-soft (falling back to `DeterministicTraversal`) is the second,
coarser layer; this is the first, per-leaf one.

The returned `meta` dict is what ends up in `RunTrace.leaf_calls` (`harness/trace/schema.py`).
**Fixed 2026-10-02** (found alongside the meter/replay bugs an independent review caught): `meta`
used to drop `usage` to `None` whenever validation failed (`outcome == "default"`) — but a call
that got a response and failed *validation* still made a real, billed API call; discarding its
usage there undercounted cost the same way the replay cache-hit bug did, just on a different path.
`usage` and the raw (pre-validation) `raw_response` are now always included whenever a call
actually happened, regardless of whether the response ended up valid.
"""

from __future__ import annotations

import time
from typing import Optional

from .schemas import SCHEMA_VERSION, LeafSchema, validate_and_clip


def leaf(llm, name: str, system: str, user: str, schema_cls: type[LeafSchema], default: LeafSchema, *,
        timeout: float = 20.0, prompt_ver: str = "1", replicate: int = 0,
        known_ids: Optional[set] = None, id_field: Optional[str] = None) -> tuple[LeafSchema, dict]:
    """Returns (result, meta). `meta` records what happened (used / default / error) for the
    trace — never raises itself; a leaf failure is always absorbed here."""
    if llm is None:
        return default, {"leaf": name, "outcome": "default", "reason": "no LLM configured (L0)"}
    t0 = time.monotonic()
    try:
        schema = schema_cls.model_json_schema()
        raw, usage = llm.complete_json(system, user, schema, timeout, leaf=name, prompt_ver=prompt_ver,
                                       schema_ver=SCHEMA_VERSION, replicate=replicate)
    except Exception as e:  # noqa: BLE001 - deliberately broad: any provider/network/budget failure defaults
        return default, {"leaf": name, "outcome": "default", "reason": f"{type(e).__name__}: {e}",
                         "wall_clock_s": round(time.monotonic() - t0, 3)}
    result = validate_and_clip(schema_cls, raw, default, known_ids=known_ids, id_field=id_field)
    outcome = "default" if result is default else "ok"
    return result, {"leaf": name, "outcome": outcome, "wall_clock_s": round(time.monotonic() - t0, 3),
                    "usage": usage.__dict__, "raw_response": raw}
