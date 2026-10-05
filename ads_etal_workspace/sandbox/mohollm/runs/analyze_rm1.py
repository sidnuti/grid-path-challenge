"""R-M1 analysis: MoHOLLM (SpacePartitioning, region method) vs global LLM baseline (`mohollm`), paired by seed.

    uv run python runs/analyze_rm1.py          (from sandbox/mohollm)

Per problem, objectives are normalised jointly over every point observed by any run of that problem
(all minimised), and hypervolume is taken w.r.t. ref point 1.1 in each objective. Each pair is compared
at an equal evaluation count n = min(len(region), len(global)), so a truncated run is compared fairly.
Writes runs/results/rm1_summary.csv and prints the paired table + cross-pair statistics (Claim 1).
"""
from __future__ import annotations

import ast, csv, json, os, sys
import numpy as np
from pymoo.indicators.hv import HV

HERE = os.path.dirname(os.path.abspath(__file__))
SANDBOX = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, SANDBOX)
from common import stats  # noqa: E402

PROBLEMS = {  # problem -> (region-method config stem, global-baseline config stem)
    "Penicillin": ("MOHOLLM-Penicillin-Context-Gemini", "mohollm-Penicillin-Gemini-Context"),
    "VehicleSafety": ("MOHOLLM-VehicleSafety-Context-Gemini", "mohollm-VehicleSafety-Context"),
    "CarSideImpact": ("MOHOLLM-CarSideImpact-Context-Gemini", "mohollm-CarSideImpact-Context"),
    "BraninCurrin": ("MOHOLLM-BraninCurrin-Gemini", "mohollm-BraninCurrin"),
}
SEEDS = [31415927, 42]
WORK = f"{HERE}/work"


def load_fvals(stem: str, seed: int) -> tuple[np.ndarray, bool]:
    """Observed objective vectors in evaluation order; second value False if the run did not finish."""
    d = f"{WORK}/full_{stem}_s{seed}_qwen3.7-flash"
    if os.path.exists(f"{d}/result.json"):
        r = json.load(open(f"{d}/result.json"))
        f = r["fvals"]
        return np.array(ast.literal_eval(f) if isinstance(f, str) else f, float), True
    # unfinished run: fall back to the per-trial checkpoint upstream writes
    # (os.walk, not glob: upstream's directory names contain "[model]" brackets)
    (path,) = [os.path.join(p, f) for p, _, fs in os.walk(f"{d}/results") if p.endswith("observed_fvals") for f in fs]
    rows = list(csv.reader(open(path)))[1:]
    return np.array([[float(v) for v in row] for row in rows], float), False


def hv_curve(F: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> list[float]:
    Z = (F - lo) / np.where(hi > lo, hi - lo, 1.0)
    ind = HV(ref_point=np.full(F.shape[1], 1.1))
    return [float(ind(Z[: i + 1])) for i in range(len(Z))]


def main() -> None:
    rows = []
    for prob, (reg, glo) in PROBLEMS.items():
        runs = {(m, s): load_fvals(stem, s) for m, stem in (("region", reg), ("global", glo)) for s in SEEDS}
        allF = np.vstack([F for F, _ in runs.values()])
        lo, hi = allF.min(0), allF.max(0)
        for s in SEEDS:
            (Fr, fin_r), (Fg, fin_g) = runs[("region", s)], runs[("global", s)]
            hr, hg = hv_curve(Fr, lo, hi), hv_curve(Fg, lo, hi)
            n = min(len(hr), len(hg))
            rows.append(dict(problem=prob, seed=s, n_equal=n, hv_region=round(hr[n - 1], 4), hv_global=round(hg[n - 1], 4),
                             diff=round(hr[n - 1] - hg[n - 1], 4), ratio=round(hr[n - 1] / hg[n - 1], 3) if hg[n - 1] else None,
                             evals_region=len(hr), evals_global=len(hg), hv_region_final=round(hr[-1], 4),
                             hv_global_final=round(hg[-1], 4), complete=fin_r and fin_g))
    os.makedirs(f"{HERE}/results", exist_ok=True)
    with open(f"{HERE}/results/rm1_summary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

    print(f"{'problem':14s} {'seed':>9s} {'n':>3s} {'HV global':>9s} {'HV region':>9s} {'diff':>7s} {'ratio':>6s}  note")
    for r in rows:
        print(f"{r['problem']:14s} {r['seed']:9d} {r['n_equal']:3d} {r['hv_global']:9.3f} {r['hv_region']:9.3f} "
              f"{r['diff']:+7.3f} {r['ratio']:6.2f}  {'' if r['complete'] else 'PARTIAL (region run stopped)'}")
    d = [r["diff"] for r in rows]
    lr = [float(np.log(r["hv_region"] / r["hv_global"])) for r in rows]
    lo_, hi_ = stats.t_ci(d)
    llo, lhi = stats.t_ci(lr)
    print(f"\nClaim 1 (region HV > global), {len(d)} problem-seed pairs at equal evaluations:")
    print(f"  region ahead in {sum(x > 0 for x in d)}/{len(d)}")
    print(f"  mean HV diff {np.mean(d):+.3f}  95% t-CI [{lo_:+.3f}, {hi_:+.3f}]  sign-flip p = {stats.sign_flip_p(d):.4f}")
    print(f"  geo-mean ratio {np.exp(np.mean(lr)):.2f}x  95% CI [{np.exp(llo):.2f}x, {np.exp(lhi):.2f}x]")
    full = [r["diff"] for r in rows if r["complete"]]
    print(f"  complete pairs only ({len(full)}): mean diff {np.mean(full):+.3f}, sign-flip p = {stats.sign_flip_p(full):.4f}")


if __name__ == "__main__":
    main()
