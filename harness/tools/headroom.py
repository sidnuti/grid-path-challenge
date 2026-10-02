"""Headroom ledger (E9, SG5-adjacent sizing input). The ROAS floor applies to the whole 42-day
eval window, not run-by-run, so running above the floor in one run carries over as spending room
in the next. Treat it like a budget: how much extra ₹/day of spend the portfolio can take on this
run while the *cumulative* projected dROAS still clears `obs.roas_floor * (1 + margin)`, spread
across the runs left by an allowance schedule (front-loaded by default, since unused headroom early
is wasted when later shocks need it more, and because the floor is checked at the end).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from gpc.observation import Observation

from ..config import Params


@dataclass
class Headroom:
    run: int
    spend_to_date: float          # portfolio ad spend so far this eval window (post-warmup), inr/day avg
    revenue_to_date: float
    droas_to_date: float
    roas_floor: float
    margin: float
    headroom_inr_day: float       # extra ₹/day of spend the floor can absorb right now, at 0 marginal ROAS
    allowance_inr_day: float      # the slice of headroom this run may actually spend


def compute_headroom(obs: Observation, params: Params) -> Headroom:
    f = obs.daily_facts[obs.daily_facts.day >= 0]
    # days 0..obs.day-1 are observable; restrict to the post-warmup window for the eval metric
    from gpc.world import WARMUP_DAYS
    post = f[f.day >= WARMUP_DAYS]
    n_days = max(post.day.nunique(), 1)
    spend = float(post.spend_inr.sum() / n_days) if len(post) else 0.0
    revenue = float(post.ad_revenue_inr.sum() / n_days) if len(post) else 0.0
    droas = revenue / spend if spend > 0 else obs.warmup_droas
    floor = obs.roas_floor * (1 + params.headroom_margin)

    # Headroom: extra ₹/day (at ~0 incremental dROAS) the cumulative average can absorb and still
    # clear the floor, i.e. solve (revenue)/(spend + h) >= floor for h, using cumulative totals so
    # far (not the daily average) because the floor is a window-cumulative constraint.
    cum_spend = float(post.spend_inr.sum()) if len(post) else 0.0
    cum_rev = float(post.ad_revenue_inr.sum()) if len(post) else 0.0
    if floor > 0:
        max_cum_spend = cum_rev / floor
        headroom_cum = max(max_cum_spend - cum_spend, 0.0)
    else:
        headroom_cum = 0.0
    headroom_day = headroom_cum / 7.0   # spendable over the coming run's 7 days

    from gpc.world import N_RUNS
    if obs.run >= N_RUNS:
        # S10: no future run exists to carry unused headroom into, so the last run spends it all
        # (still minus the margin baked into `floor` above) rather than following the schedule.
        frac = 1.0
    else:
        frac = params.allowance_frac(obs.run)
    allowance = headroom_day * frac if params.headroom_front_load else headroom_day / max(7 - obs.run + 1, 1)
    return Headroom(run=obs.run, spend_to_date=round(spend, 2), revenue_to_date=round(revenue, 2),
                     droas_to_date=round(droas, 4), roas_floor=round(floor, 4), margin=params.headroom_margin,
                     headroom_inr_day=round(headroom_day, 2), allowance_inr_day=round(allowance, 2))
