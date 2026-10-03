"""`RunTrace`: the one record System 2 (`harness/s2/*`) reads. Built from exactly what
`harness/policy.py` already computes this run — no re-computation, no extra LLM calls, no read of
anything a policy isn't allowed to see (`obs_digest` hashes public, already-observed data only).

**Both fixed 2026-10-03** (an independent review flagged both as real gaps):

- `usage` is now **this run's own usage** (`harness.llm.meter.run_usage_of`, reading `Meter`'s
  `run_usage`, reset at the start of every `recommend()`), not the lifetime running total. The
  lifetime total is still available separately as `lifetime_usage`, for anyone who wants "total
  cost of this simulation so far" rather than "cost of this one run" — previously there was only
  the lifetime number, and getting a per-run figure meant a trace reader diffing two consecutive
  JSONL lines by hand.
- `simulation_id` identifies which `simulate()` call (i.e. which policy instance — one is built
  per `simulate()` call and reused across all of its runs) a row belongs to, generated once in
  the policy's `__init__`. Without it, two `simulate()` calls both writing to
  `TRACE_DIR/<policy_name>.jsonl` (the filename has no seed/world in it) produced rows with no
  way to tell which simulation a given run belonged to.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Optional

import pandas as pd

from gpc.observation import Observation

from ..llm.meter import run_usage_of, usage_of


@dataclass
class RunTrace:
    policy: str
    simulation_id: str
    run: int
    day: int
    date: str
    params_version: str
    depth: str
    obs_digest: str
    n_candidates_raised: int
    n_candidates_cut: int
    n_candidates_explore: int
    n_precheck_dropped: int
    n_actions_shipped: int
    headroom: dict
    leaf_calls: list
    actions: list
    usage: dict
    lifetime_usage: dict
    fallback_reason: Optional[str] = None


def _obs_digest(obs: Observation) -> str:
    """A short hash of what this run's decision actually saw — campaigns/campaign_keywords'
    current state plus the daily_facts tail — so two traces can be checked for "same inputs" (a
    replay/determinism sanity check) without storing the full observation."""
    h = hashlib.sha256()
    for df in (obs.campaigns, obs.campaign_keywords, obs.daily_facts.tail(200)):
        h.update(pd.util.hash_pandas_object(df, index=True).values.tobytes())
    return h.hexdigest()[:16]


def build_trace(policy_name: str, simulation_id: str, obs: Observation, params, llm, actions: pd.DataFrame,
                run_trace: dict) -> RunTrace:
    """`run_trace` is the dict `_tools_only_recommend`/`_harness_recommend` already return
    (`policy.last_trace`) — this just reshapes it into the stable `RunTrace` schema."""
    def _n(key: str) -> int:
        v = run_trace.get(key)
        return len(v) if v is not None else 0

    fallback_reason = run_trace.get("fallback_reason")
    headroom = run_trace.get("headroom")
    headroom_dict = asdict(headroom) if headroom is not None and hasattr(headroom, "__dataclass_fields__") else {}
    return RunTrace(
        policy=policy_name, simulation_id=simulation_id, run=obs.run, day=obs.day, date=obs.date.isoformat(),
        params_version=getattr(params, "version", "0"), depth=run_trace.get("depth", "L0"),
        obs_digest=_obs_digest(obs),
        n_candidates_raised=_n("candidates_raised"),
        n_candidates_cut=_n("candidates_cut"),
        n_candidates_explore=_n("candidates_explore"),
        n_precheck_dropped=_n("precheck_dropped"),
        n_actions_shipped=len(actions),
        headroom=headroom_dict,
        leaf_calls=run_trace.get("leaf_calls", []) or [],
        actions=actions.to_dict("records") if len(actions) else [],
        usage=run_usage_of(llm),
        lifetime_usage=usage_of(llm),
        fallback_reason=fallback_reason,
    )
