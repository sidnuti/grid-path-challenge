"""Step 2 — the decision loop: one verdict per cell, plus campaign pacing facts.

Verdict per cell (campaign × keyword):
  THIN    under ₹500 spend in 14 days or under 5 orders in 28 days → hold, nothing to learn from
  CLEARS  shrunk realised direct ROAS ≥ the plan's goal for the cell
  MISSES  below goal. How much may be cut is paced by the PATIENCE LADDER on the miss streak:
          3 consecutive miss-days → up to 10% of the cell's spend, 5 → 25%, 7 → 50%.
          Fewer than 3 → wait (a one-week dip is often noise or regression to the mean).

Realised ROAS is shrunk toward the SKU × city parent with weight orders / (orders + 25), because
the goal and the realised number are the same metric read in two windows; a low cell recovers on
its own more often than not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..observation import Observation

LADDER = ((7, 0.50), (5, 0.25), (3, 0.10))
SHRINK_ORDERS = 25
THIN_SPEND_14D = 500.0
THIN_ORDERS_28D = 5
MIN_DAY_SPEND = 50.0          # a day with less spend than this neither extends nor breaks a streak


def ladder_fraction(streak: int) -> float:
    for days, frac in LADDER:
        if streak >= days:
            return frac
    return 0.0


def cell_verdicts(obs: Observation) -> pd.DataFrame:
    plan = obs.public["plan"]
    f28 = obs.window("daily_facts", 28)
    f14 = obs.window("daily_facts", 14)
    f7 = obs.window("daily_facts", 7)
    ck = obs.campaign_keywords.merge(obs.campaigns[["campaign_id", "sku_id", "city_id"]])
    ck = ck.merge(plan, on=["sku_id", "city_id", "keyword_id"], how="left")

    agg28 = f28.groupby(["campaign_id", "keyword_id"]).agg(spend_28=("spend_inr", "sum"),
                                                           rev_28=("ad_revenue_inr", "sum"),
                                                           orders_28=("ad_orders", "sum"))
    spend14 = f14.groupby(["campaign_id", "keyword_id"]).spend_inr.sum()
    a7 = f7.groupby(["campaign_id", "keyword_id"]).agg(spend_7=("spend_inr", "sum"), rev_7=("ad_revenue_inr", "sum"))
    parent = f28.groupby("campaign_id").agg(s=("spend_inr", "sum"), r=("ad_revenue_inr", "sum"))
    parent_roas = (parent.r / parent.s.replace(0, np.nan)).to_dict()
    daily = f28.groupby(["campaign_id", "keyword_id", "day"]).agg(s=("spend_inr", "sum"), r=("ad_revenue_inr", "sum"))

    rows = []
    for r in ck.itertuples():
        key = (r.campaign_id, r.keyword_id)
        s28 = float(agg28.spend_28.get(key, 0.0))
        rv28 = float(agg28.rev_28.get(key, 0.0))
        o28 = float(agg28.orders_28.get(key, 0.0))
        d28 = rv28 / s28 if s28 > 0 else np.nan
        par = parent_roas.get(r.campaign_id, np.nan)
        w = o28 / (o28 + SHRINK_ORDERS)
        if np.isnan(d28):
            shrunk = np.nan
        elif np.isnan(par):
            shrunk = d28
        else:
            shrunk = w * d28 + (1 - w) * par

        # miss streak: walk back from yesterday over days with real spend
        streak = 0
        if key[0] in daily.index.get_level_values(0):
            try:
                dd = daily.loc[key].sort_index(ascending=False)
            except KeyError:
                dd = pd.DataFrame(columns=["s", "r"])
            for _, row in dd.iterrows():
                if row.s < MIN_DAY_SPEND:
                    continue
                if row.r / row.s < r.goal_droas:
                    streak += 1
                else:
                    break

        if float(spend14.get(key, 0.0)) < THIN_SPEND_14D or o28 < THIN_ORDERS_28D:
            verdict = "THIN"
        elif shrunk >= r.goal_droas:
            verdict = "CLEARS"
        else:
            verdict = "MISSES"
        rows.append({
            "campaign_id": r.campaign_id, "sku_id": r.sku_id, "city_id": r.city_id, "keyword_id": r.keyword_id,
            "bid_cpm_inr": r.bid_cpm_inr, "active": r.active,
            "goal_droas": r.goal_droas, "marginal_floor_droas": r.marginal_floor_droas,
            "plan_budget_inr_day": r.plan_budget_inr_day,
            "spend_28d": round(s28, 2), "revenue_28d": round(rv28, 2), "orders_28d": o28,
            "spend_7d_avg": round(float(a7.spend_7.get(key, 0.0)) / 7, 2),
            "revenue_7d_avg": round(float(a7.rev_7.get(key, 0.0)) / 7, 2),
            "droas_28d": round(d28, 3) if not np.isnan(d28) else np.nan,
            "droas_shrunk": round(shrunk, 3) if not np.isnan(shrunk) else np.nan,
            "miss_streak_days": streak, "ladder_fraction": ladder_fraction(streak) if verdict == "MISSES" else 0.0,
            "verdict": verdict,
        })
    return pd.DataFrame(rows)


def campaign_pacing(obs: Observation) -> pd.DataFrame:
    """Per campaign: budget, 7-day spend, run-out days. `budget_bound` = ran out on ≥ 3 of 7 days.
    `absorption` = the share of a budget raise that turns into spend (≈ the run-out share; a
    campaign that never runs out absorbs none of a raise)."""
    cd = obs.window("campaign_daily", 7)
    g = cd.groupby("campaign_id").agg(spend_7d_avg=("spend_inr", "mean"), ran_out_days=("ran_out", "sum"))
    camp = obs.campaigns.set_index("campaign_id")
    g["daily_budget_inr"] = camp.daily_budget_inr
    g["utilization_vs_budget"] = (g.spend_7d_avg / g.daily_budget_inr).round(3)
    g["budget_bound"] = g.ran_out_days >= 3
    g["absorption"] = (g.ran_out_days / 7).clip(lower=0.0).round(3)
    last = cd.sort_values("day").groupby("campaign_id").ran_out_daypart.agg(
        lambda s: s[s != ""].mode().iloc[0] if (s != "").any() else "")
    g["typical_run_out"] = last
    return g.reset_index()
