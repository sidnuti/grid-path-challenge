"""X3.1 — dose-response of a bid.  For 12 cells (4 per keyword type, evidence tier A/B) at one recorded run state, re-simulate
the week with that cell's bid moved by -50..+50% (everything else unchanged, same market draws) and record what the
market actually did: slot mix, impressions, orders, spend, ad revenue, and total offtake. Compared with what the harness's grid
predicted for that step (`diagnostics.options`, per day x 7). X1.1 found the grid's level forecast ~1.7x high; this
experiment tests the *shape* and the *marginal* response, which is what raises and cuts rely on.

    PYTHONPATH=grid-path-challenge:. python -m experiments.x3_market.x3_1_bid_dose --seed 7 --run 3
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from gpc.market import Market
from gpc.world import build_world

from experiments.lib.direct_sim import EMPTY, simulate_week, totals
from experiments.lib.report import RESULTS, md_table, save
from experiments.lib.runs import load_latest

STEPS = (-50, -30, -10, 0, 10, 30, 50)


def pick_cells(res, run_idx: int, world, per_type: int = 4) -> pd.DataFrame:
    d = res.runs[run_idx]["trace"]["diagnostics"]
    kt = world.public["keywords"].set_index("keyword_id").keyword_type
    b = d.bids[d.bids.tier.isin(["A", "B"])].copy()
    b["ktype"] = b.keyword_id.map(kt)
    b = b[b.pred_spend_live > 0].sort_values("pred_spend_live", ascending=False)
    return b.groupby("ktype").head(per_type).reset_index(drop=True)


def _cell_week(frames, camp, kw):
    f = frames["daily_facts"]
    c = f[(f.campaign_id == camp) & (f.keyword_id == kw)]
    impr = c.impressions.sum()
    return {"impr": float(impr), "orders": float(c.ad_orders.sum()), "spend": float(c.spend_inr.sum()),
            "ad_rev": float(c.ad_revenue_inr.sum()),
            "slot1_share": float(c[c.slot == 1].impressions.sum() / impr) if impr else np.nan,
            "mean_slot": float((c.slot * c.impressions).sum() / impr) if impr else np.nan}


def one_cell(args):
    seed, run_idx, row = args
    res, _ = load_latest("l0", seed)
    world = build_world(seed)
    m = Market(world)
    r = res.runs[run_idx]
    d = res.runs[run_idx]["trace"]["diagnostics"]
    opts = d.options[(d.options.campaign_id == row["campaign_id"]) & (d.options.keyword_id == row["keyword_id"])].set_index("step_pct")
    live = float(row["live_bid"])
    out = []
    for step in STEPS:
        bid = round(live * (1 + step / 100.0), 2)
        act = pd.DataFrame([{"campaign_id": row["campaign_id"], "keyword_id": row["keyword_id"],
                             "action_type": "increase_cpm" if bid >= live else "reduce_cpm", "new_value": bid}])
        fr = simulate_week(m, r["day"], r["campaigns_before"], r["campaign_keywords_before"], act if step else EMPTY)
        cw, tt = _cell_week(fr, row["campaign_id"], row["keyword_id"]), totals(fr)
        po = opts.loc[step] if step in opts.index else None
        out.append({"seed": seed, "run": r["run"], "campaign_id": row["campaign_id"], "keyword_id": row["keyword_id"],
                    "ktype": row["ktype"], "tier": row["tier"], "step": step, "bid": bid, **cw, "offtake": tt["offtake_inr"],
                    "pred_spend_wk": float(po.pred_spend) * 7 if po is not None else np.nan,
                    "pred_rev_wk": float(po.pred_rev) * 7 if po is not None else np.nan,
                    "pred_slots": po.slots if po is not None else None})
    return out


def analyse(df: pd.DataFrame):
    base = df[df.step == 0].set_index(["campaign_id", "keyword_id"])
    df = df.join(base[["spend", "ad_rev", "offtake", "impr"]].add_prefix("b_"), on=["campaign_id", "keyword_id"])
    df["d_spend"], df["d_adrev"], df["d_offtake"] = df.spend - df.b_spend, df.ad_rev - df.b_ad_rev, df.offtake - df.b_offtake
    df["pred_d_spend"] = df.pred_spend_wk - df.groupby(["campaign_id", "keyword_id"]).pred_spend_wk.transform(lambda x: x[df.loc[x.index, "step"] == 0].iloc[0])
    by_step = df.groupby(["ktype", "step"]).agg(real_spend=("spend", "sum"), pred_spend=("pred_spend_wk", "sum"), real_rev=("ad_rev", "sum"),
                                                pred_rev=("pred_rev_wk", "sum"), slot1_share=("slot1_share", "mean"), d_offtake=("d_offtake", "sum"),
                                                d_spend=("d_spend", "sum"), d_adrev=("d_adrev", "sum")).reset_index()
    by_step["real/pred_spend"] = by_step.real_spend / by_step.pred_spend.where(by_step.pred_spend > 0)   # grid predicts 0 (no slot) at some low bids
    by_step["marginal_offtake_per_rupee"] = by_step.d_offtake / by_step.d_spend.where(by_step.d_spend.abs() > 1, np.nan)
    by_step["marginal_droas"] = by_step.d_adrev / by_step.d_spend.where(by_step.d_spend.abs() > 1, np.nan)
    return df, by_step


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--run", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--from-csv", action="store_true", help="re-analyse the saved per-step CSV instead of re-simulating")
    a = ap.parse_args()
    res, h = load_latest("l0", a.seed)
    if a.from_csv:
        raw = pd.read_csv(RESULTS / f"x3_1_bid_dose_seed{a.seed}_run{a.run}.csv")
        keep = ["seed", "run", "campaign_id", "keyword_id", "ktype", "tier", "step", "bid", "impr", "orders", "spend", "ad_rev",
                "slot1_share", "mean_slot", "offtake", "pred_spend_wk", "pred_rev_wk", "pred_slots"]
        df, by_step = analyse(raw[keep])
        cells = df[["campaign_id", "keyword_id"]].drop_duplicates()
        _write(a, df, by_step, cells, h)
        return
    world = build_world(a.seed)
    cells = pick_cells(res, a.run - 1, world)
    jobs = [(a.seed, a.run - 1, r) for r in cells.to_dict("records")]
    with ProcessPoolExecutor(a.jobs) as ex:
        rows = [x for part in ex.map(one_cell, jobs) for x in part]
    df, by_step = analyse(pd.DataFrame(rows))
    _write(a, df, by_step, cells, h)


def _write(a, df, by_step, cells, h):
    df.to_csv(RESULTS / f"x3_1_bid_dose_seed{a.seed}_run{a.run}.csv", index=False)
    md = [f"# X3.1 bid dose-response (seed {a.seed}, run {a.run}, {len(cells)} cells)", "",
          "Sums over the cells of each keyword type. `d_*` are versus the same cell at its live bid (step 0), same market draws; "
          "`pred_*` are the grid's per-day option values x 7. `marginal_*` are per rupee of spend moved.", "",
          md_table(by_step.round(2)), ""]
    save(f"x3_1_bid_dose_seed{a.seed}_run{a.run}", {"by_step": by_step.to_dict("records")}, "\n".join(md), {h})
    (RESULTS / f"x3_1_bid_dose_seed{a.seed}_run{a.run}.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
