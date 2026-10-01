"""Step 3 — grid-path traversal. The deterministic logic this challenge is about.

The order is fixed: **bid first, then move money, then hours.**

3a. BID per cell. Try the live bid ± {5, 10, 20, 30, 40, 50}% and read off each option's slot per
    daypart from the grid (slots in one daypart are alternatives — one per daypart).
      CLEARS (tier A/B): take the option with the most revenue whose average DROAS still meets the
                         cell goal AND whose extra revenue per extra ₹ (marginal DROAS) meets the
                         plan's marginal floor. Tier C cells hold: unproven, not scalable yet.
      MISSES:            step the bid down toward the best-DROAS option, but cut no more spend
                         than the patience ladder allows (10% / 25% / 50%). The spend this frees
                         becomes a SOURCE of money.
      THIN, or MISSES with a streak under 3: hold.
3b. MONEY. Two kinds of DEMAND want rupees:
      · a bid raise from 3a (its extra spend), and
      · a budget-bound campaign (ran out on ≥ 3 of 7 days) whose cells clear goal — the spend it
        loses after running out, capped at +50% of budget.
    Two kinds of SOURCE supply them:
      · rupees freed by 3a's bid cuts, at the marginal DROAS of what was cut, and
      · a GROWTH POOL of unspent plan money, priced at the portfolio ROAS floor, opened only
        while the portfolio runs ≥ 5% above the floor.
    A rupee moves from source i to demand j only if  m_j ≥ (1 + κ) · m_i  (κ = 0.2)  and
    P(m_i < m_j) > 0.8, judged from the orders behind each estimate. All moves are solved
    together as one transport LP maximising Σ x_ij (m_j − m_i). Freed money nobody qualifies
    for is RELEASED — spend goes down, which is also allowed.
3c. HOURS. A campaign that misses goal, in a daypart where every one of its keywords earns below
    its marginal floor at the chosen bids, turns that daypart off (one per campaign per run).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.stats import norm

from ..observation import Observation
from ..world import DAYPARTS
from .grid import predict_cell

BID_STEPS = (-50, -40, -30, -20, -10, -5, 0, 5, 10, 20, 30, 40, 50)
BID_FLOOR, BID_CEIL = 200.0, 10_000.0
KAPPA = 0.20
P_MIN = 0.80
RECEIVER_CAP_FRAC = 0.50
POOL_OPEN_MARGIN = 0.05
POOL_MAX_FRAC = 0.15


@dataclass
class TraversalResult:
    bids: pd.DataFrame
    options: pd.DataFrame
    sources: pd.DataFrame
    demands: pd.DataFrame
    transfers: pd.DataFrame
    dayparts: pd.DataFrame
    notes: dict = field(default_factory=dict)


def _candidates(live: float) -> list[tuple[int, float]]:
    out, seen = [], set()
    for s in BID_STEPS:
        b = float(np.clip(round(live * (1 + s / 100) / 5) * 5, BID_FLOOR, BID_CEIL))
        if b not in seen:
            seen.add(b)
            out.append((s, b))
    return out


def choose_bids(obs: Observation, grid: pd.DataFrame, verdicts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (one chosen bid per cell, every bid option considered per cell)."""
    camp = obs.campaigns.set_index("campaign_id")
    rows, opt_rows = [], []
    for v in verdicts.itertuples():
        g = grid[(grid.campaign_id == v.campaign_id) & (grid.keyword_id == v.keyword_id)]
        on = {dp: bool(camp.loc[v.campaign_id, f"on_{dp}"]) for dp in DAYPARTS}
        live = float(v.bid_cpm_inr)
        base = predict_cell(g, live, on)
        opts = []
        for step, b in _candidates(live):
            p = predict_cell(g, b, on)
            opts.append({"step": step, "bid": b, **p})
        tier = g.tier.iloc[0] if len(g) else "C"
        choice, reason = None, ""

        if not v.active:
            reason = "paused"
        elif v.verdict == "THIN":
            reason = "thin evidence — hold"
        elif v.verdict == "CLEARS":
            if tier == "C":
                reason = "clears goal but tier C (unproven) — hold"
            else:
                best = None
                for o in opts:
                    if o["spend"] <= 0:
                        continue
                    avg = o["revenue"] / o["spend"]
                    if avg < v.goal_droas:
                        continue
                    d_s, d_r = o["spend"] - base["spend"], o["revenue"] - base["revenue"]
                    if d_s > 1 and d_r / d_s < v.marginal_floor_droas:
                        continue                       # extra rupees earn below the floor
                    if best is None or o["revenue"] > best["revenue"] + 1e-6:
                        best = o
                if best is not None and best["bid"] != live:
                    choice = best
                    reason = "raise: more revenue, still ≥ goal and ≥ marginal floor" if best["bid"] > live \
                        else "lower: same revenue for less spend"
                else:
                    reason = "clears goal; no better option on the grid"
        else:  # MISSES
            frac = v.ladder_fraction
            if frac <= 0:
                reason = f"misses goal; streak {v.miss_streak_days}d < 3 — patience ladder says wait"
            else:
                max_cut = frac * max(base["spend"], v.spend_7d_avg)
                best = None
                for o in opts:
                    if o["bid"] >= live:
                        continue
                    cut = base["spend"] - o["spend"]
                    if cut > max_cut + 1e-6:
                        continue
                    roas = o["revenue"] / o["spend"] if o["spend"] > 0 else 0.0
                    key = (roas, -o["bid"])
                    if best is None or key > best[0]:
                        best = (key, o)
                if best is not None and best[1]["spend"] < base["spend"] - 1e-6:
                    choice = best[1]
                    reason = f"cut: misses goal {v.miss_streak_days}d → ladder allows {int(frac*100)}% of spend"
                elif live > BID_FLOOR:
                    # the grid sees no slot change within the ladder's limit: take the smallest step down
                    o = next((o for o in sorted(opts, key=lambda o: -o["bid"]) if o["bid"] < live), None)
                    if o is not None:
                        choice = o
                        reason = f"cut: misses goal {v.miss_streak_days}d; smallest bid step down"
                else:
                    reason = "misses goal but already at the bid floor"

        ch = choice or {"step": 0, "bid": live, **base}
        for o in opts:
            opt_rows.append({"campaign_id": v.campaign_id, "keyword_id": v.keyword_id, "step_pct": o["step"],
                             "bid": o["bid"], "pred_spend": round(o["spend"], 2), "pred_rev": round(o["revenue"], 2),
                             "pred_droas": round(o["revenue"] / o["spend"], 3) if o["spend"] > 0 else None,
                             "slots": "/".join(str(o["slots"].get(dp) or "–") for dp in DAYPARTS),
                             "chosen": o["bid"] == ch["bid"]})
        rows.append({
            "campaign_id": v.campaign_id, "keyword_id": v.keyword_id, "verdict": v.verdict, "tier": tier,
            "live_bid": live, "chosen_bid": ch["bid"], "step_pct": ch["step"] if choice else 0,
            "pred_spend_live": round(base["spend"], 2), "pred_rev_live": round(base["revenue"], 2),
            "pred_spend_new": round(ch["spend"], 2), "pred_rev_new": round(ch["revenue"], 2),
            "slots_live": "/".join(str(base["slots"].get(dp) or "–") for dp in DAYPARTS),
            "slots_new": "/".join(str(ch["slots"].get(dp) or "–") for dp in DAYPARTS),
            "reason": reason,
        })
    out = pd.DataFrame(rows)
    out["delta_spend"] = (out.pred_spend_new - out.pred_spend_live).round(2)
    out["delta_rev"] = (out.pred_rev_new - out.pred_rev_live).round(2)
    out["marginal_droas"] = np.where(out.delta_spend.abs() > 1, out.delta_rev / out.delta_spend, np.nan).round(3)
    return out, pd.DataFrame(opt_rows)


def _se(m: float, orders: float) -> float:
    return abs(m) / np.sqrt(max(orders, 1.0))


def traverse(obs: Observation, grid: pd.DataFrame, verdicts: pd.DataFrame, pacing: pd.DataFrame) -> TraversalResult:
    bids, options = choose_bids(obs, grid, verdicts)
    vk = verdicts.set_index(["campaign_id", "keyword_id"])
    pc = pacing.set_index("campaign_id")

    # ── sources ──────────────────────────────────────────────────────────────
    src = []
    for b in bids[bids.delta_spend < -1].itertuples():
        m = b.marginal_droas if not np.isnan(b.marginal_droas) else 0.0
        src.append({"source_id": f"cut:{b.campaign_id}:{b.keyword_id}", "kind": "bid_cut",
                    "campaign_id": b.campaign_id, "keyword_id": b.keyword_id,
                    "supply_inr": round(-b.delta_spend, 2), "m": round(m, 3),
                    "orders": vk.loc[(b.campaign_id, b.keyword_id), "orders_28d"]})
    f7 = obs.window("daily_facts", 7)
    port_s, port_r = f7.spend_inr.sum() / 7, f7.ad_revenue_inr.sum() / 7
    port_roas = port_r / port_s if port_s else 0.0
    plan_headroom = float((verdicts.plan_budget_inr_day - verdicts.spend_7d_avg).clip(lower=0).sum())
    pool_open = port_roas >= obs.roas_floor * (1 + POOL_OPEN_MARGIN)
    pool = min(plan_headroom, POOL_MAX_FRAC * port_s) if pool_open else 0.0
    if pool > 1:
        src.append({"source_id": "pool:growth", "kind": "growth_pool", "campaign_id": "", "keyword_id": "",
                    "supply_inr": round(pool, 2), "m": round(obs.roas_floor, 3), "orders": 400.0})
    sources = pd.DataFrame(src, columns=["source_id", "kind", "campaign_id", "keyword_id", "supply_inr", "m", "orders"])

    # ── demands ──────────────────────────────────────────────────────────────
    dem = []
    for b in bids[bids.delta_spend > 1].itertuples():
        dem.append({"demand_id": f"raise:{b.campaign_id}:{b.keyword_id}", "kind": "bid_raise",
                    "campaign_id": b.campaign_id, "keyword_id": b.keyword_id,
                    "demand_inr": round(b.delta_spend, 2), "m": round(b.marginal_droas, 3),
                    "orders": vk.loc[(b.campaign_id, b.keyword_id), "orders_28d"]})
    for cid, p in pc.iterrows():
        if not p.budget_bound:
            continue
        cv = verdicts[verdicts.campaign_id == cid]
        cb = bids[bids.campaign_id == cid]
        sw = cv.spend_7d_avg.sum()
        if sw <= 0:
            continue
        goal_w = float((cv.goal_droas * cv.spend_7d_avg).sum() / sw)
        shrunk_w = float((cv.droas_shrunk.fillna(0) * cv.spend_7d_avg).sum() / sw)
        if shrunk_w < goal_w:
            continue
        uncon_s, uncon_r = cb.pred_spend_new.sum(), cb.pred_rev_new.sum()
        act_s, act_r = cv.spend_7d_avg.sum(), cv.revenue_7d_avg.sum()
        lost_s = uncon_s - act_s
        if lost_s <= 1:
            continue
        lost_r = max(uncon_r - act_r, 0.0)
        dem.append({"demand_id": f"budget:{cid}", "kind": "budget_bound", "campaign_id": cid, "keyword_id": "",
                    "demand_inr": round(min(lost_s, RECEIVER_CAP_FRAC * p.daily_budget_inr), 2),
                    "m": round(lost_r / lost_s, 3), "orders": float(cv.orders_28d.sum())})
    demands = pd.DataFrame(dem, columns=["demand_id", "kind", "campaign_id", "keyword_id", "demand_inr", "m", "orders"])

    # ── one transport LP ─────────────────────────────────────────────────────
    pairs = []
    for i, s in sources.iterrows():
        for j, d in demands.iterrows():
            if s.campaign_id and s.campaign_id == d.campaign_id and s.keyword_id == d.keyword_id:
                continue
            if d.m < (1 + KAPPA) * s.m:
                continue
            p = 1 - norm.cdf(0, loc=d.m - s.m, scale=np.hypot(_se(s.m, s.orders), _se(d.m, d.orders)) + 1e-9)
            if p <= P_MIN:
                continue
            pairs.append((i, j, d.m - s.m, p))
    flows = []
    if pairs:
        n = len(pairs)
        c = -np.array([g for _, _, g, _ in pairs])
        A, ub = [], []
        for i in sources.index:
            A.append([1.0 if pi == i else 0.0 for pi, _, _, _ in pairs])
            ub.append(sources.loc[i, "supply_inr"])
        for j in demands.index:
            A.append([1.0 if pj == j else 0.0 for _, pj, _, _ in pairs])
            ub.append(demands.loc[j, "demand_inr"])
        res = linprog(c, A_ub=np.array(A), b_ub=np.array(ub), bounds=[(0, None)] * n, method="highs")
        if res.success:
            for (i, j, gain, p), x in zip(pairs, res.x):
                if x > 1:
                    flows.append({"source_id": sources.loc[i, "source_id"], "demand_id": demands.loc[j, "demand_id"],
                                  "amount_inr": round(x, 2), "m_source": sources.loc[i, "m"],
                                  "m_demand": demands.loc[j, "m"], "gain_per_inr": round(gain, 3),
                                  "p_better": round(p, 3)})
    transfers = pd.DataFrame(flows, columns=["source_id", "demand_id", "amount_inr", "m_source", "m_demand",
                                             "gain_per_inr", "p_better"])
    funded = transfers.groupby("demand_id").amount_inr.sum() if len(transfers) else pd.Series(dtype=float)
    used = transfers.groupby("source_id").amount_inr.sum() if len(transfers) else pd.Series(dtype=float)
    if len(demands):
        demands["funded_inr"] = demands.demand_id.map(funded).fillna(0.0).round(2)
    if len(sources):
        sources["placed_inr"] = sources.source_id.map(used).fillna(0.0).round(2)
        sources["released_inr"] = (sources.supply_inr - sources.placed_inr).where(sources.kind == "bid_cut", 0.0).round(2)

    # ── 3c hours ─────────────────────────────────────────────────────────────
    dps = []
    for cid, cv in verdicts.groupby("campaign_id"):
        sw = cv.spend_7d_avg.sum()
        if sw <= 0:
            continue
        goal_w = float((cv.goal_droas * cv.spend_7d_avg).sum() / sw)
        shrunk_w = float((cv.droas_shrunk.fillna(0) * cv.spend_7d_avg).sum() / sw)
        if shrunk_w >= goal_w:
            continue
        cb = bids[bids.campaign_id == cid].set_index("keyword_id")
        on = {dp: bool(obs.campaigns.set_index("campaign_id").loc[cid, f"on_{dp}"]) for dp in DAYPARTS}
        worst = None
        for dp in DAYPARTS:
            if not on[dp]:
                continue
            g = grid[(grid.campaign_id == cid) & (grid.daypart == dp)]
            all_below, spend_dp = True, 0.0
            for kid, row in cb.iterrows():
                gk = g[g.keyword_id == kid]
                ok = gk[gk.cpm_inr <= row.chosen_bid]
                if not len(ok):
                    continue
                r = ok.sort_values("slot").iloc[0]
                spend_dp += r.spend_day
                floor = float(cv.set_index("keyword_id").loc[kid, "marginal_floor_droas"])
                if r.droas >= floor:
                    all_below = False
            if all_below and spend_dp > 0.05 * sw:
                if worst is None or spend_dp > worst[1]:
                    worst = (dp, spend_dp)
        if worst:
            dps.append({"campaign_id": cid, "daypart_off": worst[0], "spend_day_inr": round(worst[1], 2),
                        "reason": "every keyword below its marginal floor in this daypart"})
    dayparts = pd.DataFrame(dps, columns=["campaign_id", "daypart_off", "spend_day_inr", "reason"])

    notes = {"portfolio_droas_7d": round(port_roas, 3), "roas_floor": round(obs.roas_floor, 3),
             "growth_pool_open": bool(pool_open), "growth_pool_inr": round(pool, 2),
             "plan_headroom_inr": round(plan_headroom, 2)}
    return TraversalResult(bids, options, sources, demands, transfers, dayparts, notes)
