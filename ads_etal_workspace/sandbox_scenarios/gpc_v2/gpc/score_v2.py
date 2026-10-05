"""Module F (sim v2): truth-side scoring by counterfactual. A policy never sees any of this.

Design: `design/02_simulator_v2_design.md` §7.1. With common random numbers the horizon is run twice:
under the policy, and with "all Aurel ads off from the end of warm-up". Then

    IncRev^brand = Σ_{t ≥ warm-up, s, c} offtake^policy − offtake^ads-off,   iROAS = IncRev / Spend

plus the expected four-way split of the ad orders (self / sibling / competitor / expansion, from the
shelf model's `truth_decomp` table) by cell, SKU and nest, and the legacy score.

The ads-off run bypasses the guardrails (G1/G6 would clamp a zero budget to ₹300) and is deterministic
per (seed, scenario), so it is computed once and cached.
"""
from __future__ import annotations

import pandas as pd

from .market import Market
from .runner import SimResult
from .score import summarize
from .world import N_RUNS, RUN_DAYS, WARMUP_DAYS, World

_CF_CACHE: dict[tuple, dict[str, pd.DataFrame]] = {}


def run_schedule(world: World, after_warmup=None, n_runs: int = N_RUNS) -> dict[str, pd.DataFrame]:
    """Run the market with the starting set-up, applying `after_warmup(campaigns, ck) -> (campaigns, ck)` once at
    the end of warm-up. No guardrails: for counterfactuals and mechanism probes, never for policies."""
    market = Market(world)
    campaigns = world.public["campaigns"].copy()
    ck = world.public["campaign_keywords"].copy()
    acc: dict[str, list] = {}
    for d in range(WARMUP_DAYS + n_runs * RUN_DAYS):
        if d == WARMUP_DAYS and after_warmup is not None:
            campaigns, ck = after_warmup(campaigns, ck)
        for k, v in market.simulate_day(d, campaigns, ck).items():
            acc.setdefault(k, []).append(v)
    return {k: pd.concat(v, ignore_index=True) for k, v in acc.items()}


def ads_off_tables(world: World, n_runs: int = N_RUNS) -> dict[str, pd.DataFrame]:
    """All per-day tables of the counterfactual: starting set-up during warm-up, every ad paused afterwards."""
    key = (world.seed, world.scenario, n_runs)
    if key not in _CF_CACHE:
        _CF_CACHE[key] = run_schedule(world, lambda c, k: (c, k.assign(active=False)), n_runs)
    return _CF_CACHE[key]


def ads_off(world: World, n_runs: int = N_RUNS) -> pd.DataFrame:
    """sku_city_daily of the counterfactual."""
    return ads_off_tables(world, n_runs)["sku_city_daily"]


def salvage_value(world: World, stock: pd.DataFrame | None) -> dict[str, float]:
    """₹ recovered for ephemeral-SKU units left when each SKU's live window ends (salvage_frac × ASP), by SKU."""
    cal = world.truth.get("calendar") or {}
    if stock is None or not len(stock):
        return {}
    asp = world.public["products"].set_index("sku_id").asp_inr
    out = {}
    for s in cal.get("ephemeral_skus", []):
        last = stock[(stock.sku_id == s["id"]) & (stock.day == s["live_to"])]
        out[s["id"]] = float(last.stock_end.sum() * s["salvage_frac"] * asp[s["id"]])
    return out


def score(res: SimResult, world: World) -> dict:
    """Truth-side score of one policy run (`res` from `gpc.runner.simulate` on `world`)."""
    cft = ads_off_tables(world, n_runs=len(res.runs))
    cf = cft["sku_city_daily"]
    pol = res.sku_city_daily[res.sku_city_daily.day >= WARMUP_DAYS]
    off = cf[cf.day >= WARMUP_DAYS]
    f = res.daily_facts[res.daily_facts.day >= WARMUP_DAYS]
    spend = float(f.spend_inr.sum())
    inc_by_sku = (pol.groupby("sku_id").offtake_inr.sum() - off.groupby("sku_id").offtake_inr.sum()).astype(float).round(2)
    # ephemeral stock left at the end of its window is salvaged: selling it at full price is worth more
    sal_pol = salvage_value(world, res.truth_tables.get("pub_stock_daily"))
    sal_off = salvage_value(world, cft.get("pub_stock_daily"))
    for sku in sal_pol:
        inc_by_sku[sku] = round(float(inc_by_sku.get(sku, 0.0)) + sal_pol[sku] - sal_off.get(sku, 0.0), 2)
    inc = float(inc_by_sku.sum())
    out = {
        "inc_rev_inr": round(inc, 2),
        "spend_inr": round(spend, 2),
        "iroas": round(inc / spend, 4) if spend else 0.0,
        "inc_rev_by_sku": inc_by_sku.to_dict(),
        "legacy": summarize(res),
    }
    if sal_pol:
        out["salvage_inr"] = {"policy": sal_pol, "ads_off": sal_off}
    cq, cq_off = res.truth_tables.get("truth_conquest"), cft.get("truth_conquest")
    if cq is not None:
        out["conquest_lost_units"] = {"policy": round(float(cq[cq.day >= WARMUP_DAYS].lost_units.sum()), 1),
                                      "ads_off": round(float(cq_off[cq_off.day >= WARMUP_DAYS].lost_units.sum()), 1)}
    dec = res.truth_tables.get("truth_decomp")
    if dec is not None and len(dec):
        dec = dec[dec.day >= WARMUP_DAYS]
        parts = ["ad_orders", "self", "sibling", "competitor", "expansion"]
        out["decomposition"] = {k: round(float(dec[k].sum()), 2) for k in parts}
        out["decomposition_by_sku"] = dec.groupby("sku_id")[parts].sum().round(2).to_dict("index")
        out["decomposition_by_cell"] = dec.groupby(["sku_id", "city_id", "keyword_id"])[parts].sum().round(2)
        nest = {s: n for n, spec in world.truth.get("nest_of_sku", {}).items() for s in spec}
        if nest:
            out["decomposition_by_nest"] = dec.assign(nest=dec.sku_id.map(nest)).groupby("nest")[parts].sum().round(2).to_dict("index")
    return out
