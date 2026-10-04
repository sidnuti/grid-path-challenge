"""The metric tree, computed from a SimResult (observable columns) plus the oracle (hidden ones).

    searches (oracle)  ->  impression share (oracle-assisted)  ->  impressions
        ->  orders per 1,000 impressions ("conversion")  ->  ad revenue / direct ROAS
        ->  incremental units / true iROAS (oracle)  ->  organic units  ->  offtake (the score)

**There are no clicks in the simulator.** Ad orders are Poisson on impressions x slot conversion,
so "click-through" has no counterpart; `orders_per_1k_impr` is the closest measured quantity and
is what this module reports under "conversion".
"""

from __future__ import annotations

import pandas as pd

from gpc.world import WARMUP_DAYS, World

from .oracle import keyword_types, true_incremental

DIMS = {
    "total": [],
    "week": ["week"],
    "keyword_type": ["keyword_type"],
    "sku": ["sku_id"],
    "city": ["city_id"],
    "slot": ["slot"],
    "keyword_type_week": ["keyword_type", "week"],
}


def _week(day: pd.Series) -> pd.Series:
    return ((day - WARMUP_DAYS) // 7 + 1).clip(lower=0)   # 0 = warm-up, 1..6 = runs


def facts_frame(world: World, facts: pd.DataFrame) -> pd.DataFrame:
    f = true_incremental(world, facts)
    f["keyword_type"] = f.keyword_id.map(keyword_types(world))
    f["week"] = _week(f.day)
    return f


def funnel(world: World, facts: pd.DataFrame, by: str = "total", eval_only: bool = True) -> pd.DataFrame:
    """Funnel metrics grouped by one dimension of `DIMS`. Columns: impressions, spend_inr,
    ad_orders, orders_per_1k_impr, avg_cpm, ad_revenue_inr, direct_roas, incr_units,
    cannibalised_units, incrementality (realised share of ad orders that were new), true_iroas
    (incremental revenue / spend; ASP-weighted via revenue share)."""
    f = facts_frame(world, facts)
    if eval_only:
        f = f[f.day >= WARMUP_DAYS]
    asp = world.public["products"].set_index("sku_id").asp_inr
    f["incr_revenue_inr"] = f.incr_units * f.sku_id.map(asp)
    dims = DIMS[by]
    g = f.groupby(dims) if dims else f.assign(_all=0).groupby("_all")
    out = g.agg(impressions=("impressions", "sum"), spend_inr=("spend_inr", "sum"), ad_orders=("ad_orders", "sum"),
                ad_revenue_inr=("ad_revenue_inr", "sum"), incr_units=("incr_units", "sum"),
                cannibalised_units=("cannibalised_units", "sum"), incr_revenue_inr=("incr_revenue_inr", "sum"))
    out["orders_per_1k_impr"] = out.ad_orders / out.impressions.replace(0, float("nan")) * 1000
    out["avg_cpm"] = out.spend_inr / out.impressions.replace(0, float("nan")) * 1000
    out["direct_roas"] = out.ad_revenue_inr / out.spend_inr.replace(0, float("nan"))
    out["incrementality"] = out.incr_units / out.ad_orders.replace(0, float("nan"))
    out["true_iroas"] = out.incr_revenue_inr / out.spend_inr.replace(0, float("nan"))
    return out.reset_index(drop=True if not dims else False)


def outcome(res, eval_only: bool = True) -> dict:
    """Policy-level outcome numbers straight from the emitted frames."""
    s = res.sku_city_daily
    f = res.daily_facts
    if eval_only:
        s, f = s[s.day >= WARMUP_DAYS], f[f.day >= WARMUP_DAYS]
    days = s.day.nunique()
    return {"offtake_inr": float(s.offtake_inr.sum()), "offtake_per_day": float(s.offtake_inr.sum() / days),
            "ad_units": float(s.ad_units.sum()), "organic_units": float(s.organic_units.sum()),
            "total_units": float(s.total_units.sum()), "spend_inr": float(f.spend_inr.sum()),
            "ad_revenue_inr": float(f.ad_revenue_inr.sum()),
            "direct_roas": float(f.ad_revenue_inr.sum() / f.spend_inr.sum())}


def floor_status(res) -> dict:
    """ROAS-floor accounting using the official scorer (`gpc.score.summarize`): a run that misses the floor
    has a void score, so lift is only meaningful alongside this. `margin` = direct ROAS - floor (ROAS points);
    `floor_safe_offtake_per_day` is the offtake the scorer would credit (0 when the floor is missed)."""
    from gpc.score import summarize
    s = summarize(res)
    met = bool(s["roas_constraint_met"])
    return {"met": met, "margin": float(s["direct_roas"] - s["roas_floor"]), "droas": float(s["direct_roas"]),
            "floor": float(s["roas_floor"]),
            "floor_safe_offtake_per_day": float(s["offtake_inr_per_day"]) if met else 0.0}
