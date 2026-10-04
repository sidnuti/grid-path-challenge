"""X5.1 / X5.2 — can an LLM leaf matter?  Scripted leaves (always_yes / always_no / random / oracle), one leaf at a
time and all together, at depth L2, vs the cached L0 arm on the same worlds. $0, no model call.

X5.1 bounds   paired offtake lift vs L0 per arm (t CI), floor status, answer mix
X5.2 triggers calls per leaf per world and share answered `ok` (vs defaulted), at default and recalibrated params

    PYTHONPATH=grid-path-challenge:. python -m experiments.x5_llm_aided.x5_run
"""

from __future__ import annotations

import collections
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.lib import stats
from experiments.lib.arms import LLM_LEAF_TAGS, llm_arm_parts
from experiments.lib.funnel import floor_status, outcome
from experiments.lib.report import md_table, save
from experiments.lib.runs import ALL_SEEDS, CACHE, load_latest

hashes: set[str] = set()


def arms_available():
    names = {p.name.split("__")[0] for p in CACHE.glob("llm_*__*.pkl")}
    return sorted(a for a in names if all(any(CACHE.glob(f"{a}__{s}__dev__*.pkl")) for s in ALL_SEEDS))


def calls_of(res) -> collections.Counter:
    c = collections.Counter()
    for r in res.runs:
        for m in (r["trace"] or {}).get("leaf_calls", []):
            c[(m["leaf"], m["outcome"])] += 1
    return c


def fell_back(res) -> int:
    return sum(1 for r in res.runs if "fallback_reason" in (r["trace"] or {}))


def main():
    arms = arms_available()
    base = {s: load_latest("l0", s) for s in ALL_SEEDS}
    for _, h in base.values():
        hashes.add(h)
    rows, trig = [], []
    for arm in arms:
        pset, leaves, mode = llm_arm_parts(arm)
        lifts, fs, calls, fb = [], [], collections.Counter(), 0
        for s in ALL_SEEDS:
            res, h = load_latest(arm, s)
            hashes.add(h)
            lifts.append(stats.paired_lift_pct(outcome(res)["offtake_inr"], outcome(base[s][0])["offtake_inr"]))
            fs.append(floor_status(res))
            calls += calls_of(res)
            fb += fell_back(res)
        sm = stats.summarize(lifts)
        rows.append({"params": pset, "leaf": "all" if len(leaves) > 1 else leaves[0].split("_")[0], "mode": mode,
                     "vs_l0_pct": sm["mean"], "t95": f"{sm['ci95_lo']:.3f} … {sm['ci95_hi']:.3f}", "p": sm["p_signflip"],
                     "worse/better": f"{sum(v < -1e-9 for v in lifts)}/{sum(v > 1e-9 for v in lifts)}",
                     "floor_met": f"{sum(f['met'] for f in fs)}/{len(fs)}", "min_margin": min(f["margin"] for f in fs),
                     "answered_per_world": sum(v for (lf, oc), v in calls.items() if oc == "ok") / len(ALL_SEEDS),
                     "defaulted_per_world": sum(v for (lf, oc), v in calls.items() if oc != "ok") / len(ALL_SEEDS), "fallbacks": fb})
        for (lf, oc), n in sorted(calls.items()):
            trig.append({"params": pset, "arm": arm, "leaf": lf, "outcome": oc, "calls_per_world": n / len(ALL_SEEDS)})
    df = pd.DataFrame(rows)
    order = {"always_no": 0, "random": 1, "always_yes": 2, "oracle": 3}
    if len(df):
        df["_o"] = df["mode"].map(order)
        df = df.sort_values(["params", "leaf", "_o"]).drop(columns="_o")
    tg = pd.DataFrame(trig)
    if len(tg):
        tg = tg[tg.arm.str.endswith("_all_oracle")]   # ONE arm only (summing two arms double-counted; fixed)
        tg = tg.pivot_table(index=["params", "leaf"], columns="outcome", values="calls_per_world", aggfunc="mean", fill_value=0).reset_index()  # mean over the two all-leaf arms (a sum double-counted)
    md = ["# X5.1 / X5.2 — scripted-LLM bounds and trigger rates", "",
          "Depth L2, scripted leaves, 6 dev worlds, paired vs the cached L0 arm. `default` = harness defaults (explore off, review "
          "threshold 500); `recal` = explore on (5 cells, 1000 INR/day) and review threshold 300. `always_no` is the passive answer "
          "(dampen / deny / keep mechanical leader / no explore / no veto), `always_yes` the active one, `oracle` reads hidden truth "
          "(an upper bound, not a realistic model). MDE of a 6-world paired test is roughly 0.1pp.", "",
          md_table(df.round(3)) if len(df) else "no complete arms cached yet", "",
          "## Calls per world (mean of the all-oracle and all-always-yes arms)", "", md_table(tg.round(2)) if len(tg) else "n/a", ""]
    save("x5_llm_aided", {"arms": df.to_dict("records"), "triggers": tg.to_dict("records") if len(tg) else []}, "\n".join(md), hashes)
    (Path(__file__).resolve().parents[1] / "results" / "x5_llm_aided.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
