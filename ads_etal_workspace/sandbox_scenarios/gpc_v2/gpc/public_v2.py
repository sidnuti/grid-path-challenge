"""Sim v2 public observations (design/02 §7.2), assembled from the market's per-day tables.

  - pub_stock_daily:        the brand's own gift-pack stock, sold units and stock left (it knows its stock)
  - category_share_weekly:  own-brand share of category units per nest × city, ±3 pp noise, published with
                            a 7-day lag (platform/panel category insights)
  - lift_readout:           results of `request_holdout` actions (added by the runner)

Competitor units are a hidden base (scenario `shelf.competitor_units_per_day`, by nest, scaled by city
demand share and the calendar) minus the orders Aurel's ads took from competitors, plus the Aurel
purchases competitors took through conquest.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .world import World

SHARE_NOISE_PP = 0.03
LAG_DAYS = 7
CATEGORY_STREAM = 4001


def build_public(world: World, hidden: dict, day: int, sku_city_daily: pd.DataFrame) -> dict:
    out = {}
    if "pub_stock_daily" in hidden:
        st = pd.concat(hidden["pub_stock_daily"], ignore_index=True)
        out["pub_stock_daily"] = st[st.day < day]
    if "pub_lift_readout" in hidden:                    # readouts of holdouts that finished before `day`
        out["lift_readout"] = pd.concat(hidden["pub_lift_readout"], ignore_index=True)
    if world.truth.get("shelves") and world.truth.get("shelf_spec", {}).get("competitor_units_per_day"):
        out["category_share_weekly"] = category_share_weekly(world, hidden, day, sku_city_daily)
    return out


def _cal_mult(world: World, nest_kws: list[str], d: int) -> float:
    cal = world.truth.get("_calendar_obj")
    if cal is None:
        return 1.0
    return float(np.mean([cal.search_mult(k, d) for k in nest_kws])) if nest_kws else 1.0


def category_share_weekly(world: World, hidden: dict, day: int, sku_city_daily: pd.DataFrame) -> pd.DataFrame:
    spec = world.truth["shelf_spec"]
    base = spec.get("competitor_units_per_day", {})
    if not base:
        return pd.DataFrame(columns=["week", "nest", "city_id", "own_share"])
    nest_of = {s: n for n, ss in world.truth["nest_of_sku"].items() for s in ss}
    cities = world.public["cities"].set_index("city_id").demand_share
    last_day = day - 1 - LAG_DAYS
    n_weeks = (last_day + 1) // 7
    if n_weeks <= 0:
        return pd.DataFrame(columns=["week", "nest", "city_id", "own_share"])
    sc = sku_city_daily[sku_city_daily.day < n_weeks * 7].assign(nest=lambda d: d.sku_id.map(nest_of),
                                                                  week=lambda d: d.day // 7)
    own = sc.groupby(["week", "nest", "city_id"]).total_units.sum()
    taken = pd.Series(0.0, index=own.index)
    if "truth_decomp" in hidden:
        dec = pd.concat(hidden["truth_decomp"], ignore_index=True)
        dec = dec[dec.day < n_weeks * 7].assign(nest=lambda d: d.sku_id.map(nest_of), week=lambda d: d.day // 7)
        taken = taken.add(dec.groupby(["week", "nest", "city_id"]).competitor.sum(), fill_value=0.0)
    gained = pd.Series(0.0, index=own.index)
    if "truth_conquest" in hidden:
        cq = pd.concat(hidden["truth_conquest"], ignore_index=True)
        if len(cq):
            cq = cq[cq.day < n_weeks * 7].assign(week=lambda d: d.day // 7, nest="bar")   # brand queries: bar-led
            gained = gained.add(cq.groupby(["week", "nest", "city_id"]).lost_units.sum(), fill_value=0.0)
    kws = {n: [k for k, sh in world.truth["shelves"].items()
               if any(world.truth["nest_of_sku"].get(n) and it in world.truth["nest_of_sku"][n] for it in sh.items)]
           for n in base}
    rows = []
    for (w, n, c), u in own.items():
        if n not in base:
            continue
        comp_units = sum(base[n] * cities[c] * _cal_mult(world, kws[n], d) for d in range(7 * w, 7 * w + 7))
        comp_units = max(comp_units - taken.get((w, n, c), 0.0) + gained.get((w, n, c), 0.0), 0.0)
        rng = np.random.default_rng(np.random.SeedSequence([world.seed, CATEGORY_STREAM, int(w),
                                                            sorted(base).index(n), list(cities.index).index(c)]))
        share = u / (u + comp_units) if u + comp_units > 0 else 0.0
        rows.append({"week": int(w), "nest": n, "city_id": c,
                     "own_share": round(float(np.clip(share + rng.normal(0, SHARE_NOISE_PP), 0, 1)), 4)})
    return pd.DataFrame(rows)
