"""X3.3 — causal effect of each shipped action, and how good the policy's own projections were.

For each run of an L0 simulation, re-simulate that week from the recorded state with every shipped
action removed in turn (paired, exact). The difference is the action's true effect on offtake,
spend and ad revenue over its week. It is then compared with the projection the policy/guardrails
used (`pred_delta_spend`, `pred_delta_rev`). Carry-over to later weeks is not counted.

    PYTHONPATH=grid-path-challenge:. python -m experiments.x3_market.x3_3_action_effects --seeds 7 11
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from gpc.market import Market
from gpc.world import build_world

from experiments.lib.direct_sim import simulate_week, totals
from experiments.lib.report import RESULTS, md_table, save
from experiments.lib.runs import load_latest


def one_seed(seed: int, arm: str = "l0") -> list[dict]:
    res, h = load_latest(arm, seed)
    world = build_world(seed)
    market = Market(world)
    rows = []
    for r in res.runs:
        final = r["final"].reset_index(drop=True)
        if not len(final):
            continue
        keep = ["campaign_id", "keyword_id", "action_type", "new_value"]
        base = totals(simulate_week(market, r["day"], r["campaigns_before"], r["campaign_keywords_before"], final[keep]))
        for i, a in final.iterrows():
            wo = totals(simulate_week(market, r["day"], r["campaigns_before"], r["campaign_keywords_before"],
                                      final.drop(index=i)[keep]))
            rows.append({"seed": seed, "run": r["run"], "campaign_id": a.campaign_id, "keyword_id": a.keyword_id,
                         "action_type": a.action_type, "method": str(a.reason).split(":")[0],
                         "current": a.current_value, "new": a.new_value,
                         "pred_dspend": a.pred_delta_spend, "pred_drev": a.pred_delta_rev,
                         "true_dspend": base["spend_inr"] - wo["spend_inr"],
                         "true_drev": base["ad_revenue_inr"] - wo["ad_revenue_inr"],
                         "true_dofftake": base["offtake_inr"] - wo["offtake_inr"],
                         "true_dorders": base["ad_orders"] - wo["ad_orders"], "_hash": h})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", nargs="*", type=int, default=[7, 11, 23, 42])
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args()
    with ProcessPoolExecutor(a.jobs) as ex:
        rows = [r for part in ex.map(one_seed, a.seeds) for r in part]
    df = pd.DataFrame(rows)
    hashes = set(df.pop("_hash"))
    df.to_csv(RESULTS / "x3_3_action_effects.csv", index=False)

    def calib(g):
        out = {"n": len(g)}
        for p, t in (("pred_dspend", "true_dspend"), ("pred_drev", "true_drev")):
            x, y = g[p], g[t]
            out[f"{t}_sum"] = y.sum(); out[f"{p}_sum"] = x.sum()
            out[f"{t}_ratio"] = y.sum() / x.sum() if abs(x.sum()) > 1e-9 else np.nan
            out[f"{t}_corr"] = float(np.corrcoef(x, y)[0, 1]) if len(g) > 2 and x.std() > 0 and y.std() > 0 else np.nan
        out["true_dofftake_sum"] = g.true_dofftake.sum()
        sp = g.true_dspend.sum()
        out["offtake_per_rupee"] = g.true_dofftake.sum() / sp if abs(sp) > 1e-9 else np.nan
        out["adrev_per_rupee"] = g.true_drev.sum() / sp if abs(sp) > 1e-9 else np.nan
        return pd.Series(out)

    by_type = df.groupby("action_type").apply(calib).reset_index()
    by_method = df.groupby("method").apply(calib).reset_index()
    # does the sizing ranking (iota-weighted projected ratio) match the true ranking? raises only
    rz = df[df.action_type.isin(["increase_cpm", "increase_budget"]) & (df.pred_dspend > 1)].copy()
    rz["pred_ratio"] = rz.pred_drev / rz.pred_dspend
    rz["true_ratio"] = rz.true_dofftake / rz.true_dspend.where(rz.true_dspend.abs() > 1, np.nan)
    rk = rz.dropna(subset=["true_ratio"])
    spearman = float(rk.pred_ratio.rank().corr(rk.true_ratio.rank())) if len(rk) > 3 else np.nan
    md = ["# X3.3 — causal effect of each shipped action (L0)", "",
          f"{len(df)} actions across seeds {sorted(set(df.seed))}, every run. Effects are within the action's own week, "
          "from an exact paired re-simulation with that one action removed.", "",
          "## By action type", "", md_table(by_type.round(3)), "",
          "## By method", "", md_table(by_method.round(3)), "",
          f"## Sizing rank check (raises only, n={len(rk)})", "",
          f"Spearman correlation between the projected marginal ratio (Δrev/Δspend) and the true marginal offtake per rupee: **{spearman:.3f}**.", ""]
    save("x3_3_action_effects", {"by_type": by_type.to_dict("records"), "by_method": by_method.to_dict("records"),
                                 "sizing_spearman": spearman, "n_actions": len(df)}, "\n".join(md), hashes)
    print("\n".join(md))


if __name__ == "__main__":
    main()
