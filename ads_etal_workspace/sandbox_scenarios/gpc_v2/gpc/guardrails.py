"""The guardrail layer. Runs on EVERY policy's actions — the baseline's and yours — before anything
reaches the market. A policy cannot skip it.

Per-action rules (in order):
  G0 SCHEMA            unknown campaign / keyword / action type, non-numeric value, an empty
                       daypart schedule, or a second action on the same lever → blocked
  G1 BID_BOUNDS        bid outside ₹200 – ₹10,000 → clamped
  G2 BID_STEP          bid move larger than ±50% of the live bid → clamped
  G3 TOP_SLOT          raising a bid that already holds slot 1 on ≥ 80% of last week's impressions → blocked
  G4 AVAILABILITY      any increase where the SKU's on-shelf availability in that city averaged
                       under 60% over the last 3 days → blocked (ads cannot sell what is not stocked)
  G5 BUDGET_REALIZABLE budget raise on a campaign that ran out on fewer than 2 of the last 7 days
                       → blocked (the raise would not change spend)
  G6 BUDGET_STEP       budget move beyond +50% / −30%, or below ₹300 → clamped
  G7 CELL_GOAL         raising a bid on a cell that misses its goal on tier A/B evidence, or a budget
                       on a campaign whose spend-weighted ROAS is under 90% of its goal → blocked
Portfolio rule:
  G8 PORTFOLIO_ROAS    projected portfolio direct ROAS (last 7 days + every action's projected Δ)
                       must stay ≥ the ROAS floor. If not, increases are removed, worst marginal
                       ROAS first, until it holds.

Projections use the guardrail's own grid built from observed data — never numbers a policy supplies.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .engine.grid import build_grid, predict_cell
from .engine.loop import campaign_pacing, cell_verdicts
from .observation import Observation
from .world import DAYPARTS

ACTION_TYPES = {"increase_cpm", "reduce_cpm", "pause_keyword", "increase_budget", "reduce_budget", "set_dayparts",
                "request_holdout"}                      # sim v2: a one-run pause that returns a lift readout
INCREASES = {"increase_cpm", "increase_budget"}
BID_FLOOR, BID_CEIL, BID_STEP = 200.0, 10_000.0, 0.50
BUDGET_UP, BUDGET_DOWN, BUDGET_MIN = 0.50, 0.30, 300.0
TOP_SLOT_SHARE = 0.80
OSA_MIN = 0.60
RUNOUT_MIN_DAYS = 2


def _lever(a) -> tuple:
    if a.action_type in ("increase_cpm", "reduce_cpm", "pause_keyword", "request_holdout"):
        return (a.campaign_id, a.keyword_id, "bid")
    return (a.campaign_id, "", "budget" if "budget" in a.action_type else "dayparts")


def apply_guardrails(obs: Observation, actions: pd.DataFrame, grid: pd.DataFrame | None = None
                     ) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    grid = build_grid(obs) if grid is None else grid
    verdicts = cell_verdicts(obs).set_index(["campaign_id", "keyword_id"])
    pacing = campaign_pacing(obs).set_index("campaign_id")
    camp = obs.campaigns.set_index("campaign_id")
    ck = obs.campaign_keywords.set_index(["campaign_id", "keyword_id"])
    f7 = obs.window("daily_facts", 7)
    slot1 = f7.assign(s1=f7.impressions.where(f7.slot == 1, 0)).groupby(["campaign_id", "keyword_id"]).agg(
        s1=("s1", "sum"), i=("impressions", "sum"))
    osa3 = obs.window("sku_city_daily", 3).groupby(["sku_id", "city_id"]).osa.mean()

    log: list[dict] = []
    kept: list[dict] = []
    seen: set = set()

    def note(a, rule, outcome, detail):
        log.append({"action_id": a.get("action_id", ""), "campaign_id": a.get("campaign_id", ""),
                    "keyword_id": a.get("keyword_id", ""), "action_type": a.get("action_type", ""),
                    "rule": rule, "outcome": outcome, "detail": detail})

    for a in actions.to_dict("records"):
        a.setdefault("keyword_id", "")
        a["keyword_id"] = "" if pd.isna(a["keyword_id"]) else a["keyword_id"]
        at, cid, kid = a.get("action_type"), a.get("campaign_id"), a["keyword_id"]
        # G0
        if at not in ACTION_TYPES or cid not in camp.index:
            note(a, "G0_SCHEMA", "blocked", "unknown action type or campaign"); continue
        if at in ("increase_cpm", "reduce_cpm", "pause_keyword", "request_holdout") and (cid, kid) not in ck.index:
            note(a, "G0_SCHEMA", "blocked", "keyword not in this campaign"); continue
        lever = _lever(pd.Series(a))
        if lever in seen:
            note(a, "G0_SCHEMA", "blocked", "second action on the same lever this run"); continue
        if at == "set_dayparts":
            dps = [d for d in str(a.get("new_value", "")).split(",") if d]
            if not dps or any(d not in DAYPARTS for d in dps):
                note(a, "G0_SCHEMA", "blocked", "daypart schedule must list ≥ 1 valid daypart"); continue
        elif at not in ("pause_keyword", "request_holdout"):
            try:
                a["new_value"] = float(a["new_value"])
            except (TypeError, ValueError):
                note(a, "G0_SCHEMA", "blocked", "new_value must be a number"); continue
        sku, city = camp.loc[cid, "sku_id"], camp.loc[cid, "city_id"]

        if at in ("increase_cpm", "reduce_cpm"):
            live = float(ck.loc[(cid, kid), "bid_cpm_inr"])
            a["current_value"] = live
            if (at == "increase_cpm") != (a["new_value"] > live):
                note(a, "G0_SCHEMA", "blocked", "direction does not match the value"); continue
            nv = float(np.clip(a["new_value"], BID_FLOOR, BID_CEIL))
            if nv != a["new_value"]:
                note(a, "G1_BID_BOUNDS", "clamped", f"₹{a['new_value']:.0f} → ₹{nv:.0f}")
            lo, hi = live * (1 - BID_STEP), live * (1 + BID_STEP)
            nv2 = float(np.clip(nv, lo, hi))
            if nv2 != nv:
                note(a, "G2_BID_STEP", "clamped", f"₹{nv:.0f} → ₹{nv2:.0f} (±50% of ₹{live:.0f})")
            a["new_value"] = round(nv2, 2)
        if at == "increase_cpm":
            if (cid, kid) in slot1.index and slot1.loc[(cid, kid), "i"] > 0 and \
                    slot1.loc[(cid, kid), "s1"] / slot1.loc[(cid, kid), "i"] >= TOP_SLOT_SHARE:
                note(a, "G3_TOP_SLOT", "blocked", "already at slot 1 on ≥ 80% of impressions"); continue
            v = verdicts.loc[(cid, kid)] if (cid, kid) in verdicts.index else None
            if v is not None and v.verdict == "MISSES":
                g = grid[(grid.campaign_id == cid) & (grid.keyword_id == kid)]
                if len(g) and g.tier.iloc[0] in ("A", "B"):
                    note(a, "G7_CELL_GOAL", "blocked",
                         f"cell misses goal: {v.droas_shrunk:.2f}× vs {v.goal_droas:.2f}×"); continue
        if at in INCREASES and float(osa3.get((sku, city), 1.0)) < OSA_MIN:
            note(a, "G4_AVAILABILITY", "blocked", f"availability {osa3.get((sku, city)):.0%} over 3 days"); continue
        if at in ("increase_budget", "reduce_budget"):
            cur = float(camp.loc[cid, "daily_budget_inr"])
            a["current_value"] = cur
            if (at == "increase_budget") != (a["new_value"] > cur):
                note(a, "G0_SCHEMA", "blocked", "direction does not match the value"); continue
            if at == "increase_budget":
                if int(pacing.loc[cid, "ran_out_days"]) < RUNOUT_MIN_DAYS:
                    note(a, "G5_BUDGET_REALIZABLE", "blocked",
                         f"ran out on {int(pacing.loc[cid, 'ran_out_days'])}/7 days — a raise would not spend"); continue
                cv = verdicts.loc[cid] if cid in verdicts.index.get_level_values(0) else None
                if cv is not None and cv.spend_7d_avg.sum() > 0:
                    w = cv.spend_7d_avg / cv.spend_7d_avg.sum()
                    if float((cv.droas_shrunk.fillna(0) * w).sum()) < 0.9 * float((cv.goal_droas * w).sum()):
                        note(a, "G7_CELL_GOAL", "blocked", "campaign's spend-weighted ROAS under 90% of goal"); continue
            nv = float(np.clip(a["new_value"], max(cur * (1 - BUDGET_DOWN), BUDGET_MIN), cur * (1 + BUDGET_UP)))
            if nv != a["new_value"]:
                note(a, "G6_BUDGET_STEP", "clamped", f"₹{a['new_value']:.0f} → ₹{nv:.0f}")
            a["new_value"] = round(nv, 2)
        seen.add(lever)
        kept.append(a)

    out = pd.DataFrame(kept)
    proj = project_actions(obs, out, grid, pacing) if len(out) else out
    summary = {}
    if len(out):
        out = out.join(proj[["pred_delta_spend", "pred_delta_rev"]])
        # G8 portfolio ROAS
        S = f7.spend_inr.sum() / 7
        R = f7.ad_revenue_inr.sum() / 7
        def proj_roas(df):
            return (R + df.pred_delta_rev.sum()) / max(S + df.pred_delta_spend.sum(), 1e-9)
        before = proj_roas(out)
        inc = out[out.action_type.isin(INCREASES) & (out.pred_delta_spend > 0)].copy()
        inc["m"] = inc.pred_delta_rev / inc.pred_delta_spend
        for idx in inc.sort_values("m").index:
            if proj_roas(out) >= obs.roas_floor:
                break
            note(out.loc[idx].to_dict(), "G8_PORTFOLIO_ROAS", "trimmed",
                 f"marginal {inc.loc[idx, 'm']:.2f}× pulls portfolio below the {obs.roas_floor:.2f}× floor")
            out = out.drop(idx)
        summary = {"portfolio_spend_7d_avg": round(S, 2), "portfolio_droas_7d": round(R / S, 3) if S else None,
                   "projected_droas_before_G8": round(before, 3), "projected_droas_after": round(proj_roas(out), 3),
                   "projected_delta_spend": round(out.pred_delta_spend.sum(), 2),
                   "projected_delta_rev": round(out.pred_delta_rev.sum(), 2), "roas_floor": round(obs.roas_floor, 3)}
    for a in out.to_dict("records") if len(out) else []:
        note(a, "ALL", "passed", "")
    return out.reset_index(drop=True), pd.DataFrame(log), summary


def project_actions(obs: Observation, actions: pd.DataFrame, grid: pd.DataFrame, pacing: pd.DataFrame) -> pd.DataFrame:
    """Projected Δ spend / Δ revenue per day for each action, from the guardrail's own grid."""
    camp = obs.campaigns.set_index("campaign_id")
    ck = obs.campaign_keywords.set_index(["campaign_id", "keyword_id"])
    f7 = obs.window("daily_facts", 7)
    act = f7.groupby("campaign_id").agg(s=("spend_inr", "sum"), r=("ad_revenue_inr", "sum")) / 7
    rows = []
    for a in actions.itertuples():
        on = {dp: bool(camp.loc[a.campaign_id, f"on_{dp}"]) for dp in DAYPARTS}
        ds = dr = 0.0
        cg = grid[grid.campaign_id == a.campaign_id]
        if a.action_type in ("increase_cpm", "reduce_cpm", "pause_keyword", "request_holdout"):
            g = cg[cg.keyword_id == a.keyword_id]
            live = float(ck.loc[(a.campaign_id, a.keyword_id), "bid_cpm_inr"])
            p0 = predict_cell(g, live, on)
            p1 = {"spend": 0.0, "revenue": 0.0} if a.action_type in ("pause_keyword", "request_holdout") \
                else predict_cell(g, float(a.new_value), on)
            ds, dr = p1["spend"] - p0["spend"], p1["revenue"] - p0["revenue"]
            if a.action_type == "increase_cpm" and bool(pacing.loc[a.campaign_id, "budget_bound"]):
                ds, dr = ds * float(pacing.loc[a.campaign_id, "absorption"]), dr * float(pacing.loc[a.campaign_id, "absorption"])
        elif a.action_type in ("increase_budget", "reduce_budget"):
            cur = float(camp.loc[a.campaign_id, "daily_budget_inr"])
            s_act = float(act.s.get(a.campaign_id, 0.0))
            r_act = float(act.r.get(a.campaign_id, 0.0))
            uncon_s = uncon_r = 0.0
            for kid, g in cg.groupby("keyword_id"):
                p = predict_cell(g, float(ck.loc[(a.campaign_id, kid), "bid_cpm_inr"]), on)
                uncon_s += p["spend"]; uncon_r += p["revenue"]
            if a.action_type == "increase_budget":
                lost_s = max(uncon_s - s_act, 0.0)
                ds = min((float(a.new_value) - cur) * max(float(pacing.loc[a.campaign_id, "absorption"]), 0.0), lost_s)
                m = (uncon_r - r_act) / lost_s if lost_s > 1 else (r_act / s_act if s_act else 0.0)
                dr = ds * max(m, 0.0)
            else:
                ds = -max(s_act - float(a.new_value), 0.0)
                dr = ds * (r_act / s_act if s_act else 0.0)
        elif a.action_type == "set_dayparts":
            keep = set(str(a.new_value).split(","))
            s_act = float(act.s.get(a.campaign_id, 0.0))
            for kid, g in cg.groupby("keyword_id"):
                bid = float(ck.loc[(a.campaign_id, kid), "bid_cpm_inr"])
                full = predict_cell(g, bid, on)
                after = predict_cell(g, bid, {dp: on[dp] and dp in keep for dp in DAYPARTS})
                ds += after["spend"] - full["spend"]; dr += after["revenue"] - full["revenue"]
        rows.append({"pred_delta_spend": round(ds, 2), "pred_delta_rev": round(dr, 2)})
    return pd.DataFrame(rows, index=actions.index)
