"""Goals on a simulated run (design/03 §1, §4): G-0 objective, G-1 sub-objectives, G-2 constraint values.

Every quantity is measured on the run after the fact, from public tables or the truth-side tables of the v2
market. Objectives are reported as maximised quantities here; the MoHOLLM adapter negates them (MoHOLLM
minimises everything, sandbox finding: `metrics_targets` is ignored).

Constraint values are signed slacks: ≥ 0 means satisfied (C2 and C4 need the guardrail projection, plan P4).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from gpc.runner import SimResult
from gpc.score_v2 import score
from gpc.world import DAYPARTS, WARMUP_DAYS, World

from .decode import REGION

F2_KEYWORDS = ("K08", "K01", "K03")      # S5 launch visibility, North (doc 03 G-1 f2)
F2_SKU, F2_CITY = "S5", "DEL"
NORTH_MIN = 0.25                          # C5
COMPETITION_MAX = 0.10                    # C6
K01_DEFEND_MIN = 0.70                     # C7
SIBLING_MAX = 0.30                        # C8
ROAS_TOL = 0.02                           # C9: realised direct ROAS ≥ 0.98 × warm-up


def s5_north_slot1_share(world: World, res: SimResult) -> float:
    """Share of auctions S5 wins at slot 1 on {K08, K01, K03} in the North, search-share weighted by daypart."""
    t = res.truth_tables.get("truth_slot1")
    if t is None:
        return float("nan")
    t = t[(t.day >= WARMUP_DAYS) & (t.city_id == F2_CITY) & t.keyword_id.isin(F2_KEYWORDS)]
    s5 = t[t.sku_id == F2_SKU].groupby(["day", "keyword_id", "daypart"]).share1.sum()
    c = world.public["cities"].set_index("city_id").loc[F2_CITY]
    days = range(WARMUP_DAYS, int(res.sku_city_daily.day.max()) + 1)
    num = den = 0.0
    for d in days:
        for k in F2_KEYWORDS:
            for dp in DAYPARTS:
                w = c[f"share_{dp}"]
                num += w * float(s5.get((d, k, dp), 0.0))
                den += w
    return num / den


def s6_sell_through(world: World, res: SimResult) -> float:
    st = res.truth_tables.get("pub_stock_daily")
    cal = world.truth.get("calendar") or {}
    skus = cal.get("ephemeral_skus", [])
    if st is None or not len(st) or not skus:
        return float("nan")
    s6 = skus[0]
    init = sum(s6["stock_by_city"].values())
    return float(st[st.sku_id == s6["id"]].sold.sum() / init)


def measure(world: World, res: SimResult, budget_per_day: float) -> dict:
    sc = score(res, world)
    f = res.daily_facts[res.daily_facts.day >= WARMUP_DAYS]
    spend = float(f.spend_inr.sum())
    n_days = len(res.runs) * 7
    out = {"inc_rev": sc["inc_rev_inr"], "spend": spend, "iroas": sc["iroas"],
           "droas": float(f.ad_revenue_inr.sum() / spend) if spend else 0.0,
           "f2_s5_north_slot1": s5_north_slot1_share(world, res), "f3_s6_sell_through": s6_sell_through(world, res),
           "budget": budget_per_day * n_days}
    if "decomposition" in sc:
        d = sc["decomposition"]
        out["sibling_share"] = d["sibling"] / d["ad_orders"] if d["ad_orders"] else 0.0
    if "conquest_lost_units" in sc:
        out["conquest_lost_units"] = sc["conquest_lost_units"]["policy"]
    # ── G-2 constraint slacks (≥ 0 satisfied) ──
    c = {}
    c["C1_budget"] = 1 - spend / out["budget"] if out["budget"] else 0.0
    cal = world.public.get("calendar_public")
    if cal is not None and len(cal):
        eph = cal[cal.kind.str.startswith("ephemeral")]
        outside = 0.0
        for e in eph.itertuples():
            m = (f.keyword_id == e.id) | (f.sku_id == e.id)
            outside += float(f[m & ((f.day < e.from_day) | (f.day > e.to_day))].spend_inr.sum())
        c["C3_outside_window_spend"] = -outside
    run_of = (f.day - WARMUP_DAYS) // 7
    north = f.city_id.map(REGION).eq("north")
    by_run = f.groupby(run_of).spend_inr.sum()
    c["C5_north_share"] = float((f[north].groupby(run_of[north]).spend_inr.sum().reindex(by_run.index, fill_value=0)
                                 / by_run).min() - NORTH_MIN)
    kt = world.public["keywords"].set_index("keyword_id").keyword_type
    comp = float(f[f.keyword_id.map(kt) == "competition"].spend_inr.sum())
    c["C6_competition_share"] = COMPETITION_MAX - (comp / spend if spend else 0.0)
    cq = res.truth_tables.get("truth_conquest")
    if cq is not None and len(cq):
        q = cq[(cq.day >= WARMUP_DAYS) & (cq.keyword_id == "K01") & (cq.kappa > 0)]          # any competitor presence (doc 03 C7)
        c["C7_k01_defended"] = float(q.aurel_slot1.mean() - K01_DEFEND_MIN) if len(q) else 0.0
    dec = res.truth_tables.get("truth_decomp")
    if dec is not None and len(dec):
        nest = {s: n for n, ss in world.truth["nest_of_sku"].items() for s in ss}
        dd = dec[dec.day >= WARMUP_DAYS].assign(nest=lambda x: x.sku_id.map(nest))
        g = dd.groupby(["nest", "city_id"])[["sibling", "ad_orders"]].sum()
        g = g[g.ad_orders > 0]
        c["C8_sibling_share"] = float(SIBLING_MAX - (g.sibling / g.ad_orders).max()) if len(g) else 0.0
    c["C9_realised_droas"] = float(out["droas"] / ((1 - ROAS_TOL) * res.warmup_droas) - 1)
    out["constraints"] = c
    return out
