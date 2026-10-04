"""X2 — which L0 components earn their keep?  Paired (same world) lift of every arm vs the full L0
policy and vs the no-op arm, from cached runs. t-based 95% CI, exact sign-flip p, the arm's own MDE,
and ROAS margin above the score floor (a missed floor voids the score, so lift alone is incomplete).

    PYTHONPATH=grid-path-challenge:. python -m experiments.x2_ablation.x2_run [--seeds 7 11 ...] [--tag dev6]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from gpc.score import summarize as score_summary

from experiments.lib import stats
from experiments.lib.arms import FREE_ARMS
from experiments.lib.funnel import outcome
from experiments.lib.report import md_table, save
from experiments.lib.runs import ALL_SEEDS, load_latest

hashes: set[str] = set()
_cache: dict = {}


def get(arm, seed):
    if (arm, seed) not in _cache:
        res, h = load_latest(arm, seed)
        hashes.add(h)
        s = score_summary(res)
        _cache[(arm, seed)] = {"offtake": outcome(res)["offtake_inr"], "margin": s["direct_roas"] - s["roas_floor"],
                               "met": s["roas_constraint_met"], "spend": outcome(res)["spend_inr"]}
    return _cache[(arm, seed)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", nargs="*", type=int, default=list(ALL_SEEDS))
    ap.add_argument("--tag", default="dev6")
    ap.add_argument("--arms", nargs="*", default=None)
    a = ap.parse_args()
    arms = a.arms or [x for x in dict.fromkeys(FREE_ARMS) if all((x, s) in _cache or _exists(x, s) for s in a.seeds)]
    rows = []
    for arm in arms:
        lo = [stats.paired_lift_pct(get(arm, s)["offtake"], get("l0", s)["offtake"]) for s in a.seeds]
        no = [stats.paired_lift_pct(get(arm, s)["offtake"], get("no_op", s)["offtake"]) for s in a.seeds]
        b, n = stats.summarize(lo), stats.summarize(no)
        rows.append({"arm": arm, "vs_l0_pct": b["mean"], "vs_l0_t95": f"{b['ci95_lo']:.2f} … {b['ci95_hi']:.2f}",
                     "p": b["p_signflip"], "mde": b["mde"], "worse/better seeds": f"{sum(v < 0 for v in lo)}/{sum(v > 0 for v in lo)}",
                     "vs_no_op_pct": n["mean"], "vs_no_op_t95": f"{n['ci95_lo']:.2f} … {n['ci95_hi']:.2f}",
                     "floor_met": f"{sum(get(arm, s)['met'] for s in a.seeds)}/{len(a.seeds)}",
                     "min_roas_margin": min(get(arm, s)["margin"] for s in a.seeds),
                     "mean_spend_vs_l0_pct": sum(stats.paired_lift_pct(get(arm, s)["spend"], get("l0", s)["spend"]) for s in a.seeds) / len(a.seeds)})
    df = pd.DataFrame(rows).sort_values("vs_l0_pct")
    md = (f"## X2 Ablation [{a.tag}] — {len(a.seeds)} worlds, outcome = scored offtake\n\n"
          "Negative vs_l0 = removing/isolating the component hurts. CI = Student-t; p = exact sign-flip "
          "(smallest possible 2/2^n); mde = this comparison's own 80%-power minimum detectable effect.\n\n" + md_table(df))
    print(md)
    save(f"x2_ablation_{a.tag}", {"seeds": a.seeds, "rows": rows}, md, hashes)
    (Path(__file__).resolve().parents[1] / "results" / f"x2_ablation_{a.tag}.md").write_text(md)


def _exists(arm, seed):
    try:
        get(arm, seed)
        return True
    except FileNotFoundError:
        return False


if __name__ == "__main__":
    main()
