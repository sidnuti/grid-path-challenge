"""Sizing: which bid/budget raises to ship this run, and how big, under the headroom allowance.

Per the handoff notes, this replaces the plan's `linprog` transport step with a simpler Lagrangian
multiple-choice knapsack over raise candidates only (cuts — sibling followers, competitor misses —
are unconditional: they always reduce spend and are handled by the methods directly, subject to
guardrails' own bid-step clamp):

    for each cell, pick the raise option maximising  iota * delta_rev - mu * delta_spend
    binary-search mu >= 0 so that sum(delta_spend of picks) <= the run's headroom allowance

`iota` is the SKU x keyword-type incrementality (`tools.incrementality`): a raise's *offtake*
value is `iota * delta_ad_revenue`, since the cannibalised share of extra ad revenue would have
sold organically anyway and adds no offtake. `delta_spend`/`delta_rev` come from
`gpc.guardrails.project_actions` (read-only import) so the sizing estimate matches exactly what
guardrail G8 will project when it checks the portfolio ROAS floor.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from gpc.guardrails import project_actions
from gpc.observation import Observation

from ..config import Params


@dataclass
class Candidate:
    campaign_id: str
    keyword_id: str
    action_type: str
    current_value: float
    new_value: float
    delta_spend: float
    delta_rev: float
    iota: float
    reason: str = ""

    @property
    def offtake_value(self) -> float:
        return self.iota * max(self.delta_rev, 0.0)


def project_candidates(obs: Observation, grid: pd.DataFrame, pacing: pd.DataFrame,
                       candidates: pd.DataFrame) -> pd.DataFrame:
    """Attach pred_delta_spend/pred_delta_rev to a candidate-actions frame via the guardrail's own
    projection (never a number the harness makes up)."""
    if not len(candidates):
        return candidates.assign(pred_delta_spend=[], pred_delta_rev=[])
    pacing_idx = pacing.set_index("campaign_id") if pacing.index.name != "campaign_id" else pacing
    proj = project_actions(obs, candidates, grid, pacing_idx)
    return candidates.join(proj[["pred_delta_spend", "pred_delta_rev"]])


def _value(mu: float, iota, ds, dr):
    return iota * dr - mu * np.maximum(ds, 0.0)


def select_raises(raises: pd.DataFrame, allowance_inr_day: float, params: Params) -> pd.DataFrame:
    """`raises` must have one row per candidate (>=1 per cell) with columns campaign_id,
    keyword_id, pred_delta_spend, pred_delta_rev, iota, plus the action columns. At most one
    candidate per (campaign_id, keyword_id) is kept. Binary search picks the largest mu for which
    the chosen set's total delta_spend still fits the allowance (mu=mu_hi -> nothing picked if the
    allowance is 0)."""
    if not len(raises) or allowance_inr_day <= 0:
        return raises.iloc[0:0]

    group_cols = ["campaign_id", "keyword_id", "action_type"]

    def pick(mu: float) -> pd.DataFrame:
        best_idx = (raises.assign(v=_value(mu, raises.iota, raises.pred_delta_spend, raises.pred_delta_rev))
                           .groupby(group_cols).v.idxmax())
        chosen = raises.loc[best_idx]
        return chosen[chosen.pred_delta_spend > 1]  # "no raise" / non-positive options drop out

    lo, hi = params.sizing_mu_lo, params.sizing_mu_hi
    chosen = pick(hi)
    if chosen.pred_delta_spend.sum() > allowance_inr_day:
        return chosen.sort_values("pred_delta_rev", ascending=False)  # even the tightest mu overshoots; let verify trim
    for _ in range(params.sizing_mu_iters):
        mid = (lo + hi) / 2
        chosen = pick(mid)
        spend = chosen.pred_delta_spend.sum()
        if spend > allowance_inr_day:
            lo = mid
        else:
            hi = mid
    return pick(hi)
