"""Summarise results/p3 into tables (E1: best-at-n and regret vs the in-space oracle O1; E2: hypervolume).

    PYTHONPATH=.:gpc python -m bench.report            # writes results/p3/report.md and report_e1.csv / report_e2.csv

E2 hypervolume: objectives (IncRev ₹ lakh, S5 North slot-1 %, S6 sell-through %) are maximised. For each problem
(scenario, seed) they are min-max normalised over the pooled evaluations of every arm, and the reference point is
the pooled minimum (normalised 0). So HV ∈ [0, 1] and is comparable across arms within a problem only.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

RES = Path(__file__).resolve().parents[1] / "results" / "p3"
NS = (10, 25, 50)


def load() -> list[dict]:
    out = []
    for f in sorted(RES.glob("*/*.json")):
        if f.stem.endswith("_scripted"):
            continue
        r = json.loads(f.read_text())
        out.append(r)
    return out


def best_at(evals: list[dict], n: int) -> float:
    v = [e["inc_rev"] for e in evals[:n]]
    return max(v) if v else float("nan")


def e1_table(runs: list[dict]) -> pd.DataFrame:
    rows = {}
    for r in runs:
        if r["goal"] != "G0":
            continue
        k = (r["scenario"], r["seed"])
        row = rows.setdefault(k, {"scenario": r["scenario"], "seed": r["seed"]})
        if r["arm"] == "A0":
            row["hold"] = r["hold"]["inc_rev"]
            row["traversal"] = r["traversal"]["inc_rev"]
            row["B_6wk"] = r["hold"]["budget"]
        elif r["arm"] == "O1":
            ev = r["evaluations"]
            row["O1"] = max(e["inc_rev"] for e in ev)
            row["O1_n"] = len(ev)
            for n in (100, 250, 500, 1000):
                if len(ev) >= n:
                    row[f"O1@{n}"] = best_at(ev, n)
            b = max(ev, key=lambda e: e["inc_rev"])
            row["O1_spend_over_B"] = b["spend"] / b["budget"]
            row["O1_x"] = [round(v, 2) for v in b["x"]]
        else:
            for n in NS:
                row[f"{r['arm']}@{n}"] = best_at(r["evaluations"], n)
    df = pd.DataFrame(rows.values()).sort_values(["scenario", "seed"])
    for a in ("A1", "A2", "A5"):
        if f"{a}@50" in df and "O1" in df:
            df[f"{a}_regret50"] = 1 - df[f"{a}@50"] / df["O1"]
    if "O1" in df and "hold" in df:
        df["O1_vs_hold"] = df["O1"] / df["hold"] - 1
    return df


def _hv(F: np.ndarray) -> float:
    from pymoo.indicators.hv import HV
    return float(HV(ref_point=np.zeros(F.shape[1]))(-F)) if len(F) else 0.0   # maximise ⇒ negate; ref at 0


def e2_table(runs: list[dict]) -> pd.DataFrame:
    probs: dict = {}
    for r in runs:
        if r["goal"] == "G1" and r["arm"] != "A0":
            probs.setdefault((r["scenario"], r["seed"]), []).append(r)
    rows = []
    for (sc, seed), rs in sorted(probs.items()):
        def objs(e):
            st = e["f3_s6_sell_through"]
            return [e["inc_rev"] / 1e5, 100 * e["f2_s5_north_slot1"], 100 * st if st == st else 0.0]
        pooled = np.array([objs(e) for r in rs for e in r["evaluations"]])
        lo, hi = pooled.min(0), pooled.max(0)
        span = np.where(hi > lo, hi - lo, 1.0)
        row = {"scenario": sc, "seed": seed}
        for r in rs:
            F = (np.array([objs(e) for e in r["evaluations"][:50]]) - lo) / span
            row[f"{r['arm']}_HV50"] = _hv(F)
            row[f"{r['arm']}_maxIncRev"] = max(e["inc_rev"] for e in r["evaluations"][:50])
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    runs = load()
    e1, e2 = e1_table(runs), e2_table(runs)
    e1.to_csv(RES / "report_e1.csv", index=False)
    e2.to_csv(RES / "report_e2.csv", index=False)
    fmt = lambda df: df.to_markdown(index=False, floatfmt=".4g") if len(df) else "(none)"   # noqa: E731
    md = ["# P3 baseline report ($0)", "", "## E1 (G-0): best IncRev (₹) at n evaluations; regret vs O1 at n = 50", "",
          fmt(e1.drop(columns=[c for c in e1 if c == "O1_x"])), ""]
    num = [c for c in e1.columns if c.endswith("regret50") or c == "O1_vs_hold"]
    if num:
        md += ["### Mean over seeds", "", fmt(e1.groupby("scenario")[num].mean().reset_index()), ""]
    md += ["## E2 (G-1): hypervolume after 50 evaluations (pooled normalisation per problem)", "", fmt(e2), ""]
    (RES / "report.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
