"""Sizing: which bid/budget raises to ship this run, under the headroom allowance.

`iota` is the SKU x keyword-type incrementality (`tools.incrementality`): a raise's *offtake*
value is `iota * delta_ad_revenue`, since the cannibalised share of extra ad revenue would have
sold organically anyway and adds no offtake. `delta_spend`/`delta_rev` come from
`gpc.guardrails.project_actions` (read-only import) so the sizing estimate matches exactly what
guardrail G8 will project when it checks the portfolio ROAS floor.

**Rewritten 2026-10-03** (an independent review measured the original version shipping raises
17-114x the headroom allowance, across multiple seeds and runs). The original design was a
Lagrangian multiple-choice knapsack — "for each cell, pick the raise option maximising `iota *
delta_rev - mu * delta_spend`; binary-search `mu` so total `delta_spend` fits the allowance" — on
the premise that each cell offers a *menu* of raise sizes to choose between (per the plan's own
framing, the thing `scipy.optimize.linprog` would have sized continuously). It doesn't: every
caller (`m_reprice_raises`, `m_budget_raises`, `shock_raises`) emits exactly **one** candidate per
cell — the engine's single already-chosen target bid — never a menu. So the "pick the best option
for this cell" step was choosing among a group of size 1, which a `groupby().idxmax()` always
returns regardless of `mu`; the per-cell choice was happening, `mu` was just never able to
influence it at any of the 110 cells this was checked against. The binary search therefore always
converged on the same total spend regardless of `mu`, and whenever that already exceeded the
allowance, the harshest-tested-`mu` branch "gave up" and shipped the whole unconstrained set
(`chosen.sort_values(...)`, no `allowance_inr_day` check at all) rather than degrading gracefully
— which is the 17-114x.

Now a plain 0/1 knapsack over whole-cell candidates (there is only one size per cell to decide
in or out of, so that's what the actual candidate shape supports): rank by marginal ratio
`iota * delta_rev / delta_spend` and greedily take candidates, highest ratio first, while
cumulative `delta_spend` stays under the allowance. This is the correct, simple solution to the
problem the candidates *actually* pose; reintroducing a real multiple-choice sizing LP would need
the upstream methods to emit a menu of bid-step options per cell first (they have access to that
menu via `diag.options` already, just never plumb more than one row through) — flagged as a
larger, separate change, not folded into this fix.
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


def select_raises(raises: pd.DataFrame, allowance_inr_day: float, params: Params) -> pd.DataFrame:
    """`raises` has one row per candidate — in practice exactly one per (campaign_id, keyword_id,
    action_type), since every current caller emits a single candidate per cell (see the module
    docstring) — with columns `pred_delta_spend`, `pred_delta_rev`, `iota`, plus the action
    columns. Ranks by marginal ratio (`iota * delta_rev / delta_spend`) and greedily takes
    candidates, highest ratio first, while cumulative `delta_spend` stays within
    `allowance_inr_day`. A non-positive ratio or `delta_spend` never gets picked, same as the
    old filter's `pred_delta_spend > 1` effectively enforced."""
    if not len(raises) or allowance_inr_day <= 0:
        return raises.iloc[0:0]

    live = raises[raises.pred_delta_spend > 1].copy()
    if not len(live):
        return live
    live["_ratio"] = live.iota * live.pred_delta_rev / live.pred_delta_spend.clip(lower=1e-9)
    live = live[live._ratio > 0].sort_values("_ratio", ascending=False)
    cum_spend = live.pred_delta_spend.cumsum()
    return live[cum_spend <= allowance_inr_day].drop(columns="_ratio")
