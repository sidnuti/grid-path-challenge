"""Analyse R-C2 (3 seeds x 3 agents x 2 biases, 52 weeks, minimax-m3). Paired by seed (same market seed + same bias)."""
import glob, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common import stats

rows = []
for f in glob.glob("runs/results/rc2_full_seed*_s*_*.csv"):
    b = os.path.basename(f)[:-4].split("_")       # rc2 full seedN sNN agent... bias
    seed, sim = b[2], b[3]; bias = b[-1]; agent = "_".join(b[4:-1])
    d = pd.read_csv(f)
    rows.append(dict(seed=seed, bias=bias, agent=agent, weeks=len(d), total_profit=d.profit.sum(), weekly_sd=d.profit.std(),
                     final_trust=d.brand_trust.iloc[-1], trust_delta=d.brand_trust.iloc[-1] - 0.7, final_price=d.price.iloc[-1],
                     loss_weeks=(d.profit < 0).mean(), min_price=d.price.min(), max_price=d.price.max()))
R = pd.DataFrame(rows)
R.to_csv("runs/results/rc2_summary_by_run.csv", index=False)
order = ["llm_only", "llm_symbolic", "full_chimera"]
pd.set_option("display.width", 200, "display.float_format", lambda x: f"{x:,.2f}")
print("complete runs:", len(R), "| weeks per run:", sorted(R.weeks.unique()))
g = R.groupby(["bias", "agent"]).agg(n=("seed", "count"), profit_mean=("total_profit", "mean"), profit_sd=("total_profit", "std"),
        sd_week=("weekly_sd", "mean"), trust=("final_trust", "mean"), trust_d=("trust_delta", "mean"), loss=("loss_weeks", "mean")).reindex(
        [(b, a) for b in ("decrease", "increase") for a in order])
print(g.to_string())
print("\nper seed total profit:")
print(R.pivot_table(index=["bias", "agent"], columns="seed", values="total_profit").reindex([(b, a) for b in ("decrease", "increase") for a in order]).to_string())
print("\npaired differences (seed-paired), total profit:")
for bias in ("decrease", "increase"):
    for a, b in (("llm_symbolic", "llm_only"), ("full_chimera", "llm_symbolic"), ("full_chimera", "llm_only")):
        x = R[(R.bias == bias) & (R.agent == a)].set_index("seed").total_profit
        y = R[(R.bias == bias) & (R.agent == b)].set_index("seed").total_profit
        d = (x - y).dropna().tolist()
        lo, hi = stats.t_ci(d)
        print(f"  {bias:8s} {a:13s} - {b:13s}: mean {np.mean(d):>11,.0f}  t-CI95 [{lo:>11,.0f},{hi:>11,.0f}]  wins {sum(v > 0 for v in d)}/{len(d)}  per-seed {[round(v) for v in d]}")
print("\nweekly profit sd (lower = steadier): Full lowest in", sum(
    R[(R.bias == b) & (R.agent == "full_chimera")].set_index("seed").weekly_sd.lt(
        R[(R.bias == b) & (R.agent != "full_chimera")].groupby("seed").weekly_sd.min()).sum() for b in ("decrease", "increase")), "of 6 (bias, seed) cells")
