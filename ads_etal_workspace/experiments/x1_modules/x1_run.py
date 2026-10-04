"""X1 — score each L0 module against hidden truth, from cached L0 runs (+ `l0rec` for shocks).

X1.1 forecast   per-cell live-bid spend/revenue forecast vs the realised week, on campaigns whose bids and
                budgets were untouched, split by whether the campaign ran out of budget that week
X1.2 iota       incrementality estimate vs truth (incrementality x organic damping), by keyword type and run
X1.3 siblings   does the chosen leader have the highest true incremental value per impression?
X1.4 headroom   banked headroom / allowance vs the slack actually left at the end of the window
X1.5 precheck   guardrail block rate on what precheck let through
X1.6 shocks     precision / recall / lead time of detect_shocks against the injected shocks

    PYTHONPATH=grid-path-challenge:. python -m experiments.x1_modules.x1_run
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gpc.world import RUN_DAYS, build_world

from experiments.lib.oracle import cell_truth
from experiments.lib.report import md_table, save
from experiments.lib.runs import ALL_SEEDS, load_latest

hashes: set[str] = set()


def get(arm, seed):
    res, h = load_latest(arm, seed)
    hashes.add(h)
    return res


# ── X1.1 forecast ─────────────────────────────────────────────────────────────
def x1_1():
    rows = []
    for seed in ALL_SEEDS:
        r = get("l0", seed)
        f, cd = r.daily_facts, r.campaign_daily
        for x in r.runs:
            d0 = x["day"]
            b = x["trace"]["diagnostics"].bids.set_index(["campaign_id", "keyword_id"])
            touched = set(x["final"].campaign_id)
            wk = f[(f.day >= d0) & (f.day < d0 + RUN_DAYS)].groupby(["campaign_id", "keyword_id"])[["spend_inr", "ad_revenue_inr"]].sum() / RUN_DAYS
            ran_out = set(cd[(cd.day >= d0) & (cd.day < d0 + RUN_DAYS) & cd.ran_out].campaign_id)
            m = b[["pred_spend_live", "pred_rev_live", "tier"]].join(wk, how="left").fillna({"spend_inr": 0.0, "ad_revenue_inr": 0.0}).reset_index()
            m = m[~m.campaign_id.isin(touched)]
            m["stratum"] = np.where(m.campaign_id.isin(ran_out), "ran_out", "not_run_out")
            for (stratum, tier), g in m.groupby(["stratum", "tier"]):
                rows.append({"seed": seed, "run": x["run"], "stratum": stratum, "tier": tier, "n": len(g),
                             "pred_spend": g.pred_spend_live.sum(), "real_spend": g.spend_inr.sum(),
                             "pred_rev": g.pred_rev_live.sum(), "real_rev": g.ad_revenue_inr.sum()})
    d = pd.DataFrame(rows)
    g = d.groupby(["stratum", "tier"]).agg(cell_runs=("n", "sum"), pred_spend=("pred_spend", "sum"), real_spend=("real_spend", "sum"),
                                           pred_rev=("pred_rev", "sum"), real_rev=("real_rev", "sum")).reset_index()
    g["spend_real/pred"] = g.real_spend / g.pred_spend
    g["rev_real/pred"] = g.real_rev / g.pred_rev
    g["droas_real"] = g.real_rev / g.real_spend
    g["droas_pred"] = g.pred_rev / g.pred_spend
    s = d.groupby("stratum").agg(pred_spend=("pred_spend", "sum"), real_spend=("real_spend", "sum"),
                                 pred_rev=("pred_rev", "sum"), real_rev=("real_rev", "sum")).reset_index()
    s["spend_real/pred"] = s.real_spend / s.pred_spend
    s["rev_real/pred"] = s.real_rev / s.pred_rev
    return g, s


# ── X1.2 iota ─────────────────────────────────────────────────────────────────
def x1_2():
    rows = []
    for seed in ALL_SEEDS:
        w = build_world(seed)
        kt = w.public["keywords"].set_index("keyword_id").keyword_type
        t = w.truth
        ck = w.public["campaign_keywords"].merge(w.public["campaigns"][["campaign_id", "sku_id"]])
        ck["type"] = ck.keyword_id.map(kt)
        ck["inc"] = [t["keywords"][k]["incrementality"] for k in ck.keyword_id]
        ck["inc_eff"] = [t["keywords"][k]["incrementality"] * t["organic_damp"].get((s, k), 1.0) for s, k in zip(ck.sku_id, ck.keyword_id)]
        truth = ck.groupby(["sku_id", "type"])[["inc", "inc_eff"]].mean()
        r = get("l0", seed)
        for x in r.runs:
            for (sku, typ), est in x["trace"]["iota"].items():
                if (sku, typ) in truth.index:
                    rows.append({"seed": seed, "run": x["run"], "type": typ, "est": est, "inc": truth.loc[(sku, typ), "inc"],
                                 "inc_eff": truth.loc[(sku, typ), "inc_eff"]})
    d = pd.DataFrame(rows)
    d["err_eff"] = d.est - d.inc_eff
    by_type = d.groupby("type").agg(n=("est", "count"), mean_est=("est", "mean"), mean_true_inc=("inc", "mean"), mean_true_eff=("inc_eff", "mean"),
                                    mae_vs_eff=("err_eff", lambda x: x.abs().mean()), bias_vs_eff=("err_eff", "mean"),
                                    corr_eff=("est", lambda x: np.corrcoef(x, d.loc[x.index, "inc_eff"])[0, 1] if x.std() > 0 else np.nan)).reset_index()
    by_run = d.groupby("run").agg(n=("est", "count"), mae_vs_eff=("err_eff", lambda x: x.abs().mean()), bias=("err_eff", "mean")).reset_index()
    return by_type, by_run


# ── X1.3 siblings ─────────────────────────────────────────────────────────────
def x1_3():
    rows = []
    for seed in ALL_SEEDS:
        ct = cell_truth(build_world(seed)).set_index(["campaign_id", "keyword_id"]).true_value_per_impr
        r = get("l0", seed)
        for x in r.runs:
            mk = x["trace"]["sibling_markets"]
            if not len(mk):
                continue
            for (city, kw), g in mk[mk.is_contested].groupby(["city_id", "keyword_id"]):
                tv = np.array([ct.get((c, kw), np.nan) for c in g.campaign_id])
                if np.isnan(tv).any() or len(g) < 2:
                    continue
                lead = g.is_leader.values
                if lead.sum() != 1:
                    continue
                best = int(np.argmax(tv))
                sc = g.leader_score.values
                srt = np.sort(sc)[::-1]
                rows.append({"seed": seed, "run": x["run"], "n_sib": len(g), "correct": bool(lead[best]),
                             "value_ratio_chosen_vs_best": float(tv[lead][0] / tv[best]) if tv[best] > 0 else np.nan,
                             "near_tie": bool(srt[0] > 0 and (srt[0] - srt[1]) / srt[0] < 0.10),
                             "rank_corr": float(pd.Series(sc).corr(pd.Series(tv), method="spearman")) if len(g) > 2 else np.nan})
    d = pd.DataFrame(rows)
    if not len(d):
        return d, d
    s = d.groupby("near_tie").agg(markets=("correct", "count"), leader_correct=("correct", "mean"),
                                  mean_value_ratio=("value_ratio_chosen_vs_best", "mean")).reset_index()
    return d, s


# ── X1.4 headroom ─────────────────────────────────────────────────────────────
def x1_4():
    rows = []
    for seed in ALL_SEEDS:
        r = get("l0", seed)
        from gpc.score import summarize
        sc = summarize(r)
        f = r.daily_facts[r.daily_facts.day >= 28]
        floor = sc["roas_floor"]
        slack_total = float(f.ad_revenue_inr.sum() / floor - f.spend_inr.sum())          # ₹ of extra spend the floor could still absorb at 0 ROAS
        for x in r.runs:
            h = x["trace"]["headroom"]
            shipped_raise = float(x["final"][x["final"].action_type.isin(["increase_cpm", "increase_budget"])].pred_delta_spend.sum()) if len(x["final"]) else 0.0
            rows.append({"seed": seed, "run": x["run"], "headroom_inr_day": h.headroom_inr_day, "allowance_inr_day": h.allowance_inr_day,
                         "shipped_raise_pred_dspend": shipped_raise, "end_slack_total": slack_total, "end_margin": sc["direct_roas"] - floor})
    d = pd.DataFrame(rows)
    by_run = d.groupby("run").agg(headroom_inr_day=("headroom_inr_day", "mean"), allowance_inr_day=("allowance_inr_day", "mean"),
                                  shipped_raise_pred_dspend=("shipped_raise_pred_dspend", "mean")).reset_index()
    end = d.groupby("seed").agg(end_slack_inr_total=("end_slack_total", "first"), end_margin=("end_margin", "first")).reset_index()
    return by_run, end


# ── X1.5 precheck leakage ─────────────────────────────────────────────────────
def x1_5():
    rows = []
    for seed in ALL_SEEDS:
        r = get("l0", seed)
        for x in r.runs:
            gl = x["guardrail_log"]
            if gl is None or not len(gl):
                continue
            ex = gl[gl.rule != "ALL"] if "rule" in gl else gl
            blocked = gl[gl.outcome != "passed"]
            rows.append({"seed": seed, "run": x["run"], "proposed": len(x["proposed"]), "shipped": len(x["final"]),
                         "blocked": int(len(x["proposed"]) - len(x["final"])), "dropped_by_precheck": len(x["trace"]["precheck_dropped"])})
    d = pd.DataFrame(rows)
    return d.agg({"proposed": "sum", "shipped": "sum", "blocked": "sum", "dropped_by_precheck": "sum"}).to_frame().T


# ── X1.6 shocks ───────────────────────────────────────────────────────────────
def x1_6():
    rows = []
    for seed in ALL_SEEDS:
        try:
            r, h = load_latest("l0rec", seed)
        except FileNotFoundError:
            continue
        hashes.add(h)
        w = build_world(seed)
        camp = w.public["campaigns"].set_index("campaign_id")
        truth = w.truth["shocks"]
        for x in r.runs:
            sh = x["trace"].get("shocks")
            if sh is None or not len(sh):
                continue
            sh = sh.copy()
            sh["sku"] = sh.campaign_id.map(camp.sku_id)
            sh["city"] = sh.campaign_id.map(camp.city_id)
            obs_day = x["day"]
            for s in truth:
                kind = s["kind"]
                flag = {"osa": "shock_osa_drop", "price": "shock_cpm", "demand": "shock_reach"}[kind]
                match = pd.Series(True, index=sh.index)
                if "sku_id" in s:
                    match &= sh.sku == s["sku_id"]
                if "city_id" in s:
                    match &= sh.city == s["city_id"]
                if "keyword_ids" in s:
                    match &= sh.keyword_id.isin(s["keyword_ids"])
                # shock visible in the detector's recent window [obs_day-7, obs_day) -> overlap with [from, to]
                active = (s["from_day"] < obs_day) and (s.get("to_day", 10**9) >= obs_day - 7)
                flagged = sh[flag] & (sh.direction == "surge") if kind == "demand" else sh[flag]
                rows.append({"seed": seed, "run": x["run"], "obs_day": obs_day, "kind": kind, "active": active,
                             "tp": int((flagged & match).sum()) if active else 0,
                             "fn": int((~flagged & match).sum()) if active else 0,
                             "fp_in_scope": int((flagged & match).sum()) if not active else 0,
                             "fp_out_of_scope": int((flagged & ~match).sum()), "from_day": s["from_day"]})
    d = pd.DataFrame(rows)
    if not len(d):
        return d, d
    agg = d.groupby("kind").agg(tp=("tp", "sum"), fn=("fn", "sum"), fp_before_onset=("fp_in_scope", "sum"),
                                fp_elsewhere=("fp_out_of_scope", "sum")).reset_index()
    agg["recall"] = agg.tp / (agg.tp + agg.fn).replace(0, np.nan)
    agg["precision"] = agg.tp / (agg.tp + agg.fp_elsewhere + agg.fp_before_onset).replace(0, np.nan)
    lead = []
    for (seed, kind), g in d.groupby(["seed", "kind"]):
        hit = g[(g.tp > 0)].sort_values("run")
        lead.append({"seed": seed, "kind": kind, "onset_day": int(g.from_day.iloc[0]),
                     "first_detect_obs_day": int(hit.obs_day.iloc[0]) if len(hit) else None,
                     "lead_days": int(hit.obs_day.iloc[0] - g.from_day.iloc[0]) if len(hit) else None})
    return agg, pd.DataFrame(lead)


def main():
    f_cell, f_all = x1_1()
    i_type, i_run = x1_2()
    s_d, s_sum = x1_3()
    h_run, h_end = x1_4()
    p = x1_5()
    sh_agg, sh_lead = x1_6()
    md = ["# X1 — modules scored against truth (L0, dev worlds, 6 seeds)", ""]
    md += ["## X1.1 Live-bid forecast vs the realised week", "",
           "Only campaigns with no shipped action that run (so the forecast is of an unchanged bid). `real/pred` < 1 = the "
           "grid over-forecasts. `ran_out` = the campaign hit its budget that week (the grid forecasts unconstrained demand).", "",
           md_table(f_all.round(3)), "", "By tier:", "", md_table(f_cell.round(3)), ""]
    md += ["## X1.2 Incrementality estimate vs truth", "",
           "`inc_eff` = true incrementality x organic damping, the quantity ι estimates.", "", md_table(i_type.round(3)), "",
           "By run (does the estimate improve with data?):", "", md_table(i_run.round(3)), ""]
    md += ["## X1.3 Sibling leader vs true value per impression", ""]
    md += [md_table(s_sum.round(3)) if len(s_sum) else "no contested markets", ""]
    md += ["## X1.4 Headroom and allowance vs what was left", "",
           "`headroom_inr_day`: spend/day the floor could absorb at zero marginal ROAS. `end_slack_inr_total`: the same quantity "
           "left unspent at the end of the window (₹, whole window).", "", md_table(h_run.round(1)), "", md_table(h_end.round(2)), ""]
    md += ["## X1.5 What precheck lets through", "", md_table(p), ""]
    md += ["## X1.6 Shock detection vs injected shocks", ""]
    md += ([md_table(sh_agg.round(3)), "", md_table(sh_lead)] if len(sh_agg) else ["no l0rec runs cached yet"]) + [""]
    save("x1_modules", {"forecast": f_all.to_dict("records"), "forecast_tier": f_cell.to_dict("records"), "iota": i_type.to_dict("records"),
                        "iota_run": i_run.to_dict("records"), "siblings": s_sum.to_dict("records"),
                        "headroom": h_run.to_dict("records"), "headroom_end": h_end.to_dict("records"),
                        "precheck": p.to_dict("records"), "shocks": sh_agg.to_dict("records"), "shock_lead": sh_lead.to_dict("records")},
         "\n".join(md), hashes)
    from pathlib import Path
    (Path(__file__).resolve().parents[1] / "results" / "x1_modules.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
