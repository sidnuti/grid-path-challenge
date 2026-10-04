"""W0 — reconcile the old runtime report's "+0.82% vs baseline" (harness commit 0b73557) with today's +0.23% (483ea9e).
`gpc/` is identical in the two commits, so the market and the baseline are the same; only the harness differs. Paired over dev6.

Hypothesis: 0b73557's sizing shipped every raise when the set overshot the allowance (its own fix note: 17-114x the allowance),
i.e. it effectively had no headroom gate, so old L0 ~ today's `no_headroom_gate` arm.

    PYTHONPATH=grid-path-challenge:. python -m experiments.w0.w0_run
"""

from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd

from experiments.lib import stats
from experiments.lib.funnel import floor_status, outcome
from experiments.lib.report import RESULTS, md_table, save
from experiments.lib.runs import ALL_SEEDS, CACHE, load_latest

OLD = "0b73557"


def old(arm, seed):
    return pickle.loads((CACHE / f"old{OLD}_{arm}__{seed}__dev__{OLD}.pkl").read_bytes())


def main():
    hashes = set()
    rows, checks = [], []
    for s in ALL_SEEDS:
        cur = {a: load_latest(a, s) for a in ("l0", "baseline", "no_op", "no_headroom_gate")}
        hashes |= {h for _, h in cur.values()}
        o = old("l0", s)
        off = lambda r: outcome(r)["offtake_inr"]
        spend = lambda r: outcome(r)["spend_inr"]
        fs = floor_status(o)
        rows.append({"seed": s,
                     "old_l0_vs_baseline": stats.paired_lift_pct(off(o), off(cur["baseline"][0])),
                     "new_l0_vs_baseline": stats.paired_lift_pct(off(cur["l0"][0]), off(cur["baseline"][0])),
                     "old_l0_vs_new_l0": stats.paired_lift_pct(off(o), off(cur["l0"][0])),
                     "old_l0_vs_no_gate": stats.paired_lift_pct(off(o), off(cur["no_headroom_gate"][0])),
                     "no_gate_vs_baseline": stats.paired_lift_pct(off(cur["no_headroom_gate"][0]), off(cur["baseline"][0])),
                     "old_spend_vs_new_l0_pct": stats.paired_lift_pct(spend(o), spend(cur["l0"][0])),
                     "old_floor_met": fs["met"], "old_margin": fs["margin"],
                     "new_margin": floor_status(cur["l0"][0])["margin"],
                     "old_actions_shipped": sum(len(r["final"]) for r in o.runs),
                     "new_actions_shipped": sum(len(r["final"]) for r in cur["l0"][0].runs)})
        bp = CACHE / f"old{OLD}_baseline__{s}__dev__{OLD}.pkl"
        if bp.exists():   # sanity: same gpc -> the old worktree's baseline must equal today's exactly
            checks.append({"seed": s, "baseline_identical": off(pickle.loads(bp.read_bytes())) == off(cur["baseline"][0])})
    d = pd.DataFrame(rows)
    summ = []
    for c in ("old_l0_vs_baseline", "new_l0_vs_baseline", "no_gate_vs_baseline", "old_l0_vs_new_l0", "old_l0_vs_no_gate", "old_spend_vs_new_l0_pct"):
        sm = stats.summarize(list(d[c]))
        summ.append({"comparison": c, "mean_pct": sm["mean"], "t95": f"{sm['ci95_lo']:.2f} … {sm['ci95_hi']:.2f}", "p": sm["p_signflip"],
                     "min": sm["min"], "max": sm["max"]})
    summ = pd.DataFrame(summ)
    md = ["# W0 — old (0b73557) vs new (483ea9e) harness, dev6, paired", "",
          "`gpc/` is identical in both commits; only the harness differs. Old runs are simulated from a git worktree at 0b73557.", "",
          md_table(summ.round(3)), "", "Per seed:", "", md_table(d.round(3)), "",
          "Baseline identity check (old worktree vs today): " + (", ".join(f"seed {c['seed']}: {c['baseline_identical']}" for c in checks) or "not run"), ""]
    save("w0_old_vs_new_harness", {"summary": summ.to_dict("records"), "per_seed": d.to_dict("records"), "checks": checks},
         "\n".join(md), hashes | {OLD})
    (RESULTS / "w0_old_vs_new_harness.md").write_text("\n".join(md))
    print("\n".join(md))
    assert all(c["baseline_identical"] for c in checks), "old worktree baseline differs from today's: gpc is not the same, comparison invalid"


if __name__ == "__main__":
    main()
