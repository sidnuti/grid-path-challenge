"""X0 — are the measurements right?  X0.1 books, X0.2 oracle, X0.3 noise floor + MDE,
X0.4 where lift comes from, X0.5 lift by week.

    PYTHONPATH=grid-path-challenge:. python -m experiments.x0_measurement.x0_run
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gpc.market import Market
from gpc.world import WARMUP_DAYS, build_world

from experiments.lib import stats
from experiments.lib.funnel import floor_status, funnel, outcome
from experiments.lib.oracle import clean_mask, day_potential, week_states
from experiments.lib.report import md_table, save
from experiments.lib.runs import ALL_SEEDS, SEARCH_SEEDS, load_latest

hashes: set[str] = set()


def get(arm, seed):
    res, h = load_latest(arm, seed)
    hashes.add(h)
    return res


# ── X0.1 books ────────────────────────────────────────────────────────────────
def x0_1():
    rows = []
    for arm in ("no_op", "baseline", "l0"):
        for seed in ALL_SEEDS:
            r = get(arm, seed)
            s, f = r.sku_city_daily, r.daily_facts
            w = build_world(seed)
            asp = w.public["products"].set_index("sku_id").asp_inr
            e1 = float((s.offtake_inr - s.total_units * s.sku_id.map(asp)).abs().max())
            e2 = int((s.total_units - s.organic_units - s.ad_units).abs().max())
            g = f.groupby(["day", "sku_id", "city_id"]).agg(o=("ad_orders", "sum"), rev=("ad_revenue_inr", "sum"))
            m = s.set_index(["day", "sku_id", "city_id"]).join(g, how="left").fillna({"o": 0, "rev": 0})
            e3 = int((m.ad_units - m.o).abs().max())
            e4 = float((m.ad_revenue_inr - m.rev).abs().max())
            clip = int((s.organic_units == 0).sum())
            rows.append({"arm": arm, "seed": seed, "offtake_vs_units_x_asp": e1, "total_vs_org_plus_ad": e2,
                         "ad_units_vs_facts": e3, "ad_rev_vs_facts": e4, "zero_organic_rows": clip,
                         "rows": len(s), "pass": e1 < 0.02 and e2 == 0 and e3 == 0 and e4 < 0.02})
    df = pd.DataFrame(rows)
    return df


# ── X0.2 oracle ───────────────────────────────────────────────────────────────
def x0_2(seeds=(7, 101), days=(3, 20, 30, 41, 50, 62)):
    rows = []
    for seed in seeds:
        w = build_world(seed)
        res = get("l0", seed)
        m = Market(w)
        st = week_states(w, res.runs)
        facts, cd = res.daily_facts, res.campaign_daily
        for day in days:
            camp, ck = st[day]
            sr, pot = day_potential(m, day, camp, ck)
            emitted = facts[facts.day == day].set_index(["campaign_id", "keyword_id", "daypart", "slot"]).impressions
            allp = pot.set_index(["campaign_id", "keyword_id", "daypart", "slot"])
            allp = allp[allp.impressions_potential >= 1.0]
            clean = pot[clean_mask(w, pot, cd, day)].set_index(["campaign_id", "keyword_id", "daypart", "slot"])
            clean = clean[clean.impressions_potential >= 1.0]
            jc = clean.join(emitted, how="left")
            err = (jc.impressions_potential.round() - jc.impressions).abs()
            ja = allp.join(emitted, how="left").fillna({"impressions": 0})
            trunc_gap = float((ja.impressions_potential.sum() - ja.impressions.sum()) / ja.impressions_potential.sum())
            rows.append({"seed": seed, "day": day, "rows_clean": len(jc), "rows_all": len(ja),
                         "share_clean": len(jc) / len(ja), "max_abs_err": float(err.max()), "p99_abs_err": float(err.quantile(.99)),
                         "missing_in_emitted": int(jc.impressions.isna().sum()),
                         "impr_lost_to_budget_share": trunc_gap})
    return pd.DataFrame(rows)


# ── X0.3 noise floor ──────────────────────────────────────────────────────────
def lifts(arm, ref, seeds):
    out = []
    for s in seeds:
        out.append(stats.paired_lift_pct(outcome(get(arm, s))["offtake_per_day"], outcome(get(ref, s))["offtake_per_day"]))
    return out


def x0_3():
    res = {}
    aa = outcome(get("l0", 7))["offtake_inr"] - outcome(get("l0", 7))["offtake_inr"]
    res["aa_difference_inr"] = aa
    for name, arm, ref in (("l0_vs_baseline", "l0", "baseline"), ("l0_vs_no_op", "l0", "no_op"),
                           ("baseline_vs_no_op", "baseline", "no_op")):
        x = lifts(arm, ref, ALL_SEEDS)
        s = stats.summarize(x)
        s["values"] = [round(v, 4) for v in x]
        s["mde_n6"] = stats.minimum_detectable_effect(s["sd"], 6)
        s["mde_n12"] = stats.minimum_detectable_effect(s["sd"], 12)
        s["mde_n24"] = stats.minimum_detectable_effect(s["sd"], 24)
        s["worlds_for_0.1pp"] = stats.worlds_needed(s["sd"], 0.1)
        s["worlds_for_0.2pp"] = stats.worlds_needed(s["sd"], 0.2)
        res[name] = s
    return res


# ── X0.4 where lift comes from ────────────────────────────────────────────────
def x0_4():
    out = []
    for seed in ALL_SEEDS:
        w = build_world(seed)
        asp = w.public["products"].set_index("sku_id").asp_inr
        base_ref = {}
        for arm in ("no_op", "baseline", "l0"):
            r = get(arm, seed)
            s = r.sku_city_daily[r.sku_city_daily.day >= WARMUP_DAYS]
            a = asp.reindex(s.sku_id).values
            base_ref[arm] = {"offtake": float(s.offtake_inr.sum()), "ad_value": float((s.ad_units * a).sum()),
                             "organic_value": float((s.organic_units * a).sum()),
                             "spend": float(r.daily_facts[r.daily_facts.day >= WARMUP_DAYS].spend_inr.sum())}
        for ref in ("baseline", "no_op"):
            d = {k: base_ref["l0"][k] - base_ref[ref][k] for k in base_ref["l0"]}
            out.append({"seed": seed, "vs": ref, **d})
    df = pd.DataFrame(out)
    # by keyword type, true-incremental view, l0 vs baseline
    types = []
    for seed in ALL_SEEDS:
        w = build_world(seed)
        ft = {arm: funnel(w, get(arm, seed).daily_facts, "keyword_type").set_index("keyword_type") for arm in ("baseline", "l0", "no_op")}
        for kt in ft["l0"].index:
            for ref in ("baseline", "no_op"):
                types.append({"seed": seed, "vs": ref, "keyword_type": kt,
                              "d_spend": ft["l0"].loc[kt, "spend_inr"] - ft[ref].loc[kt, "spend_inr"],
                              "d_ad_orders": ft["l0"].loc[kt, "ad_orders"] - ft[ref].loc[kt, "ad_orders"],
                              "d_incr_units": ft["l0"].loc[kt, "incr_units"] - ft[ref].loc[kt, "incr_units"],
                              "d_cannibalised": ft["l0"].loc[kt, "cannibalised_units"] - ft[ref].loc[kt, "cannibalised_units"]})
    bt = pd.DataFrame(types)
    # direct vs true iROAS by type, per arm, averaged over seeds
    roas = []
    for arm in ("no_op", "baseline", "l0"):
        for seed in ALL_SEEDS:
            ft = funnel(build_world(seed), get(arm, seed).daily_facts, "keyword_type")
            ft["arm"], ft["seed"] = arm, seed
            roas.append(ft)
    rr = pd.concat(roas).groupby(["arm", "keyword_type"])[["direct_roas", "true_iroas", "orders_per_1k_impr", "avg_cpm", "incrementality"]].mean().reset_index()
    return df, bt, rr


# ── X0.5 lift by week ─────────────────────────────────────────────────────────
def x0_5():
    rows = []
    for seed in ALL_SEEDS:
        per = {}
        for arm in ("no_op", "baseline", "l0"):
            s = get(arm, seed).sku_city_daily
            s = s[s.day >= WARMUP_DAYS].assign(week=lambda d: (d.day - WARMUP_DAYS) // 7 + 1)
            per[arm] = s.groupby("week").offtake_inr.sum()
        cum = {a: per[a].cumsum() for a in per}
        for wk in per["l0"].index:
            rows.append({"seed": seed, "week": int(wk),
                         "l0_vs_baseline_pct": (per["l0"][wk] / per["baseline"][wk] - 1) * 100,
                         "l0_vs_no_op_pct": (per["l0"][wk] / per["no_op"][wk] - 1) * 100,
                         "cum_l0_vs_baseline_pct": (cum["l0"][wk] / cum["baseline"][wk] - 1) * 100})
    return pd.DataFrame(rows)


# ── X0.6 floor margin: lift only counts if the ROAS floor is met ───────────────
def x0_6():
    rows = []
    for arm in ("no_op", "baseline", "l0"):
        fs = [floor_status(get(arm, s)) for s in ALL_SEEDS]
        rows.append({"arm": arm, "floor_met": f"{sum(f['met'] for f in fs)}/{len(fs)}",
                     "mean_margin": float(np.mean([f["margin"] for f in fs])), "min_margin": min(f["margin"] for f in fs),
                     "mean_floor_safe_offtake_per_day": float(np.mean([f["floor_safe_offtake_per_day"] for f in fs]))})
    return pd.DataFrame(rows)


def main():
    books = x0_1()
    orc = x0_2()
    noise = x0_3()
    lift_split, by_type, roas = x0_4()
    weekly = x0_5()
    floor = x0_6()

    md = ["# X0 — measurement checks", ""]
    md += ["## X0.1 Do the books balance?", "",
           f"{int(books['pass'].sum())} of {len(books)} (arm × seed) runs pass every identity. "
           "Zero-organic rows are days where `organic − cannibalised` was clipped at 0, i.e. hidden cannibalisation.", "",
           md_table(books.groupby("arm").agg(runs=("seed", "count"), all_pass=("pass", "all"),
                                              max_offtake_err=("offtake_vs_units_x_asp", "max"),
                                              max_unit_err=("ad_units_vs_facts", "max"),
                                              zero_organic_rows=("zero_organic_rows", "sum")).reset_index()), ""]
    md += ["## X0.2 Does the oracle reconstruct what the market served?", "",
           "Clean auctions only (no sibling in the market ran out of budget). `impr_lost_to_budget_share` is the share "
           "of *potential* impressions never served because budgets ran out (all auctions).", "",
           md_table(orc.round(4)), ""]
    md += ["## X0.3 Noise floor and minimum detectable effect", "",
           f"A/A difference (same arm twice): **{noise['aa_difference_inr']} ₹**.", ""]
    rows = []
    for k in ("l0_vs_baseline", "l0_vs_no_op", "baseline_vs_no_op"):
        v = noise[k]
        rows.append({"comparison": k, "n": v["n"], "mean_pct": v["mean"], "sd_pct": v["sd"], "min": v["min"], "max": v["max"],
                     "ci95": f"{v['ci95_lo']:.2f} … {v['ci95_hi']:.2f}", "MDE n=6": v["mde_n6"], "MDE n=12": v["mde_n12"],
                     "MDE n=24": v["mde_n24"], "worlds for 0.1pp": v["worlds_for_0.1pp"], "worlds for 0.2pp": v["worlds_for_0.2pp"]})
    md += [md_table(pd.DataFrame(rows)), ""]
    md += ["## X0.4 Where does the lift come from?", "",
           "Mean over seeds of (l0 − reference), ₹ over the 42 evaluation days.", "",
           md_table(lift_split.groupby("vs")[["offtake", "ad_value", "organic_value", "spend"]].mean().reset_index(), "{:,.0f}"), "",
           "By keyword type (true-incremental view), mean over seeds:", "",
           md_table(by_type.groupby(["vs", "keyword_type"])[["d_spend", "d_ad_orders", "d_incr_units", "d_cannibalised"]].mean().reset_index(), "{:,.1f}"), "",
           "Direct vs. true iROAS and funnel metrics by keyword type (mean over seeds):", "",
           md_table(roas.round(3)), ""]
    md += ["## X0.5 Lift by week", "",
           md_table(weekly.groupby("week")[["l0_vs_baseline_pct", "l0_vs_no_op_pct", "cum_l0_vs_baseline_pct"]].agg(["mean", "min", "max"]).round(3)
                    .pipe(lambda d: d.set_axis([f"{a} {b}" for a, b in d.columns], axis=1)).reset_index()), ""]
    md += ["## X0.6 Floor margin (a missed floor voids the score)", "",
           "Margin = direct ROAS − floor, ROAS points, over the 6 dev worlds.", "", md_table(floor), ""]
    save("x0_measurement", {"floor": floor.to_dict("records"), "books": books.to_dict("records"), "oracle": orc.to_dict("records"), "noise": noise,
                            "lift_split": lift_split.to_dict("records"), "by_type": by_type.to_dict("records"),
                            "roas_by_type": roas.to_dict("records"), "weekly": weekly.to_dict("records")},
         "\n".join(md), hashes)
    print("\n".join(md))


if __name__ == "__main__":
    main()
