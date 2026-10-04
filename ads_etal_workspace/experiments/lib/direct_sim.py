"""Simulation loops that expose what `gpc.runner.simulate` hides.

* `simulate_scheduled` is the runner's loop with actions supplied per run and **no guardrails**
  (bids/budgets only clamped to their hard bounds), so the market can be probed directly — e.g.
  a +50% bid on a cell the guardrails would block. It also calls an `on_obs` hook with the real
  `Observation` at each decision point, which lets a "recorder" log module outputs.
* `simulate_week` runs just the 7 days of one run from a given state. The market has no memory
  beyond its inputs (every draw is indexed by day and entity), so any week can be re-simulated
  from the campaign/bid state recorded in a SimResult — a cheap, exactly paired counterfactual.
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import pandas as pd

from gpc.market import Market
from gpc.observation import Observation
from gpc.runner import ROAS_TOLERANCE, _days, apply_actions
from gpc.world import N_RUNS, RUN_DAYS, WARMUP_DAYS, World

BID_FLOOR, BID_CEIL, BUDGET_MIN = 200.0, 10_000.0, 300.0
EMPTY = pd.DataFrame(columns=["campaign_id", "keyword_id", "action_type", "new_value"])


def clamp_actions(a: pd.DataFrame) -> pd.DataFrame:
    a = a.copy()
    if not len(a):
        return a
    bid = a.action_type.isin(["increase_cpm", "reduce_cpm"])
    a.loc[bid, "new_value"] = a.loc[bid, "new_value"].astype(float).clip(BID_FLOOR, BID_CEIL)
    bud = a.action_type.isin(["increase_budget", "reduce_budget"])
    a.loc[bud, "new_value"] = a.loc[bud, "new_value"].astype(float).clip(lower=BUDGET_MIN)
    return a


def _frames(acc):
    return {k: pd.concat(v, ignore_index=True) for k, v in acc.items()}


def simulate_scheduled(world: World, schedule: Optional[dict] = None, on_obs: Optional[Callable] = None,
                       n_runs: int = N_RUNS) -> dict:
    """`schedule[run]` is a DataFrame of actions (or a callable `obs -> DataFrame`). Returns a dict
    with the three frames and `runs` (campaigns/bids before each run's actions)."""
    schedule = schedule or {}
    market = Market(world)
    campaigns = world.public["campaigns"].copy()
    ck = world.public["campaign_keywords"].copy()
    acc = {"daily_facts": [], "campaign_daily": [], "sku_city_daily": []}
    _days(market, 0, WARMUP_DAYS, campaigns, ck, acc)
    f = pd.concat(acc["daily_facts"])
    warm = float(f.ad_revenue_inr.sum() / f.spend_inr.sum())
    runs = []
    for r in range(1, n_runs + 1):
        day = WARMUP_DAYS + (r - 1) * RUN_DAYS
        obs = Observation(run=r, day=day, public=world.public, campaigns=campaigns.copy(), campaign_keywords=ck.copy(),
                          roas_floor=warm * (1 - ROAS_TOLERANCE), warmup_droas=warm, **_frames(acc))
        if on_obs is not None:
            on_obs(obs)
        a = schedule.get(r, EMPTY)
        a = a(obs) if callable(a) else a
        runs.append({"run": r, "day": day, "campaigns_before": campaigns.copy(), "campaign_keywords_before": ck.copy(),
                     "actions": a})
        campaigns, ck = apply_actions(campaigns, ck, clamp_actions(a))
        _days(market, day, RUN_DAYS, campaigns, ck, acc)
    return {**_frames(acc), "runs": runs, "warmup_droas": warm}


def simulate_week(market: Market, day: int, campaigns: pd.DataFrame, ck: pd.DataFrame,
                  actions: pd.DataFrame = EMPTY) -> dict[str, pd.DataFrame]:
    """The 7 days from `day` with `actions` applied to the given state (guardrails NOT applied —
    pass already-guardrailed `final` actions to reproduce a run exactly)."""
    camp, k = apply_actions(campaigns, ck, actions)
    acc = {"daily_facts": [], "campaign_daily": [], "sku_city_daily": []}
    _days(market, day, RUN_DAYS, camp, k, acc)
    return _frames(acc)


def totals(frames: dict) -> dict:
    s, f = frames["sku_city_daily"], frames["daily_facts"]
    return {"offtake_inr": float(s.offtake_inr.sum()), "spend_inr": float(f.spend_inr.sum()),
            "ad_revenue_inr": float(f.ad_revenue_inr.sum()), "ad_orders": float(f.ad_orders.sum()),
            "impressions": float(f.impressions.sum())}
