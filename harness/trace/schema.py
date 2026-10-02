"""`RunTrace`: the one record System 2 (`harness/s2/*`) reads. Built from exactly what
`harness/policy.py` already computes this run — no re-computation, no extra LLM calls, no read of
anything a policy isn't allowed to see (`obs_digest` hashes public, already-observed data only).

`usage` is **cumulative for this policy instance up to and including this run**, not a per-run
delta — `Meter` (`harness/llm/meter.py`) only tracks a running total, and diffing two traces'
`usage` (this run's and the previous run's, both written to the same JSONL file) gets a per-run
number without this schema needing to track a baseline itself. `harness/s2/reward.py` does that
diffing, not this module.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Optional

import pandas as pd

from gpc.observation import Observation

from ..llm.meter import usage_of


@dataclass
class RunTrace:
    policy: str
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
    fallback_reason: Optional[str] = None


def _obs_digest(obs: Observation) -> str:
    """A short hash of what this run's decision actually saw — campaigns/campaign_keywords'
    current state plus the daily_facts tail — so two traces can be checked for "same inputs" (a
    replay/determinism sanity check) without storing the full observation."""
    h = hashlib.sha256()
    for df in (obs.campaigns, obs.campaign_keywords, obs.daily_facts.tail(200)):
        h.update(pd.util.hash_pandas_object(df, index=True).values.tobytes())
    return h.hexdigest()[:16]


def build_trace(policy_name: str, obs: Observation, params, llm, actions: pd.DataFrame, run_trace: dict) -> RunTrace:
    """`run_trace` is the dict `_tools_only_recommend`/`_harness_recommend` already return
    (`policy.last_trace`) — this just reshapes it into the stable `RunTrace` schema."""
    def _n(key: str) -> int:
        v = run_trace.get(key)
        return len(v) if v is not None else 0

    fallback_reason = run_trace.get("fallback_reason")
    headroom = run_trace.get("headroom")
    headroom_dict = asdict(headroom) if headroom is not None and hasattr(headroom, "__dataclass_fields__") else {}
    return RunTrace(
        policy=policy_name, run=obs.run, day=obs.day, date=obs.date.isoformat(),
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
        usage=usage_of(llm),
        fallback_reason=fallback_reason,
    )
