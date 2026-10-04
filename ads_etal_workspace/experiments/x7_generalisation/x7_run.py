"""X7.3 — does the dev-world picture hold when the world differs? Paired lift vs L0 and vs no-op, floor status, on the
perturbed worlds (7 value variants: iota, auction sigma, appeal, intent; and P1-P6 shock-schedule worlds), 3 fresh seeds each.

    PYTHONPATH=grid-path-challenge:. python -m experiments.x7_generalisation.x7_run
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from experiments.lib import stats
from experiments.lib.funnel import floor_status, outcome
from experiments.lib.report import md_table, save
from experiments.lib.runs import CACHE, load_latest
from experiments.lib.scenarios import scenario_paths

SEEDS = (303, 304, 305)
ARMS = ["no_op", "l0", "no_headroom_gate", "gate_min3000", "no_cuts", "sm_r1500_c1.0"]
hashes: set[str] = set()


def get(arm, seed, sc):
    res, h = load_latest(arm, seed, sc)
    hashes.add(h)
    return {"off": outcome(res)["offtake_inr"], **floor_status(res)}


def main():
    rows = []
    paths = scenario_paths()
    for name, path in paths.items():
        stem = Path(path).stem
        if not all(list(CACHE.glob(f"{a}__{s}__{stem}__*.pkl")) for a in ARMS for s in SEEDS):
            continue
        fam = "shock" if name.startswith("P") else "value"
        for arm in ARMS:
            d = [get(arm, s, path) for s in SEEDS]
            l0 = [get("l0", s, path) for s in SEEDS]
            no = [get("no_op", s, path) for s in SEEDS]
            for s_i, s in enumerate(SEEDS):
                rows.append({"scenario": name, "family": fam, "arm": arm, "seed": s,
                             "vs_l0": stats.paired_lift_pct(d[s_i]["off"], l0[s_i]["off"]),
                             "vs_no_op": stats.paired_lift_pct(d[s_i]["off"], no[s_i]["off"]),
                             "met": d[s_i]["met"], "margin": d[s_i]["margin"]})
    df = pd.DataFrame(rows)
    if not len(df):
        print("no complete scenarios cached yet")
        return
    by_arm = []
    for (fam, arm), g in df.groupby(["family", "arm"]):
        s = stats.summarize(list(g.vs_l0))
        by_arm.append({"family": fam, "arm": arm, "n_worlds": len(g), "vs_l0_pct": s["mean"], "t95": f"{s['ci95_lo']:.2f} … {s['ci95_hi']:.2f}",
                       "worse/better": f"{(g.vs_l0 < -1e-9).sum()}/{(g.vs_l0 > 1e-9).sum()}", "floor_met": f"{int(g.met.sum())}/{len(g)}",
                       "min_margin": g.margin.min(), "vs_no_op_pct": g.vs_no_op.mean()})
    by_arm = pd.DataFrame(by_arm)
    per_sc = df[df.arm != "l0"].pivot_table(index="scenario", columns="arm", values="vs_l0", aggfunc="mean").round(2).reset_index()
    fails = df[~df.met].groupby(["scenario", "arm"]).size().reset_index(name="floor_misses")
    md = ["# X7.3 — generalisation to perturbed worlds", "",
          f"{df.scenario.nunique()} worlds x {len(SEEDS)} seeds (303-305). Lift in % vs full L0 on the same world+seed (t-CI over world x seed pairs; "
          "pairs within a scenario share its parameters, so the CIs are optimistic).", "", md_table(by_arm.round(3)), "",
          "Mean lift vs L0 by scenario:", "", md_table(per_sc), "",
          "Floor misses:", "", md_table(fails) if len(fails) else "none", ""]
    save("x7_generalisation", {"by_arm": by_arm.to_dict("records"), "rows": df.to_dict("records")}, "\n".join(md), hashes)
    (Path(__file__).resolve().parents[1] / "results" / "x7_generalisation.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
