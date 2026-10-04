"""Counterfactual helpers. `ReplayPolicy` re-emits recorded per-run proposals, so a single action
can be removed (or a whole week's actions replaced) while every other decision stays identical —
the paired design X3.3 needs. Effects are read within the affected week only, because later weeks
of a *reactive* policy would diverge for reasons other than the removed action."""

from __future__ import annotations

import pandas as pd

from gpc.observation import Observation
from gpc.policy import Policy
from gpc.runner import simulate
from gpc.world import RUN_DAYS, WARMUP_DAYS, build_world


class ReplayPolicy(Policy):
    name = "replay"

    def __init__(self, proposals_by_run: dict[int, pd.DataFrame], drop: dict[int, list[int]] | None = None,
                 extra: dict[int, pd.DataFrame] | None = None):
        self.proposals = proposals_by_run
        self.drop = drop or {}
        self.extra = extra or {}
        self.last_trace = {}

    def recommend(self, obs: Observation) -> pd.DataFrame:
        a = self.proposals.get(obs.run)
        if a is None or not len(a):
            a = pd.DataFrame(columns=["campaign_id", "keyword_id", "action_type", "new_value", "reason"])
        a = a.reset_index(drop=True)
        if obs.run in self.drop:
            a = a.drop(index=[i for i in self.drop[obs.run] if i in a.index]).reset_index(drop=True)
        if obs.run in self.extra:
            a = pd.concat([a, self.extra[obs.run]], ignore_index=True)
        return a


def proposals_of(res) -> dict[int, pd.DataFrame]:
    return {r["run"]: r["proposed"].reset_index(drop=True) for r in res.runs}


def week_totals(res, run: int) -> dict:
    """Offtake / spend / ad revenue / orders over the 7 days of `run` (1-based)."""
    d0 = WARMUP_DAYS + (run - 1) * RUN_DAYS
    s = res.sku_city_daily
    f = res.daily_facts
    s = s[(s.day >= d0) & (s.day < d0 + RUN_DAYS)]
    f = f[(f.day >= d0) & (f.day < d0 + RUN_DAYS)]
    return {"offtake_inr": float(s.offtake_inr.sum()), "spend_inr": float(f.spend_inr.sum()),
            "ad_revenue_inr": float(f.ad_revenue_inr.sum()), "ad_orders": float(f.ad_orders.sum())}


def replay(seed: int, scenario: str, policy: Policy):
    return simulate(build_world(seed, scenario), policy, verbose=False)
