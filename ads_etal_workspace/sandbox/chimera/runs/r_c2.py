"""R-C2: 3 agents x {decrease(volume), increase(margin)} bias over N weeks, via upstream `run_agent_scenario`, with the LLM
routed through OpenRouter (record/replay + ledger). Upstream is imported, never edited.

    SANDBOX_LLM_MODE=record uv run python runs/r_c2.py --pilot          # 4 weeks
    SANDBOX_LLM_MODE=replay uv run python runs/r_c2.py --pilot          # identical CSVs at $0
    uv run python runs/r_c2.py --weeks 52 --salt seed0
"""
import argparse
import os
import sys
import tempfile
import time
import warnings
from pathlib import Path

if os.environ.get("PYTHONHASHSEED") != "0":      # upstream orders candidates via list(set(str)); needs a fixed hash seed to replay
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable] + sys.argv)

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE / "upstream"), str(HERE.parent)]
warnings.filterwarnings("ignore")

from common import ledger, openrouter as orr          # noqa: E402
from adapters import llm                              # noqa: E402

GOALS = {"decrease": "Maximize profit through VOLUME. Lower prices drive demand.",
         "increase": "Maximize profit through MARGINS. Higher prices mean higher profits."}
AGENTS = ["llm_only", "llm_symbolic", "full_chimera"]
ITEM = "chimera_minimax"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true", help="4 weeks")
    ap.add_argument("--weeks", type=int, default=52)
    ap.add_argument("--agents", default=",".join(AGENTS))
    ap.add_argument("--biases", default="decrease,increase")
    ap.add_argument("--salt", default="seed0")
    ap.add_argument("--sim-seed", type=int, default=42, help="market simulator seed (upstream hard-codes 42)")
    ap.add_argument("--out", default=str(HERE / "runs" / "results"))
    a = ap.parse_args()
    weeks = 4 if a.pilot else a.weeks
    rz = os.environ.get("SANDBOX_REASONING", "default")
    tag = f"{'pilot' if a.pilot else 'full'}_{a.salt}" + ("" if rz == "default" else f"_rz-{rz}")

    import preprint.three_agent_comparative_benchmark as b
    llm.install(b, item=ITEM, salt=a.salt)
    b.NUM_WEEKS = weeks
    work = Path(tempfile.mkdtemp(prefix="chimera_work_"))
    orig_engine = b.CausalEngineV6                                       # keep upstream from writing models/*.pkl

    def engine(**k):
        e = orig_engine(**{**k, "data_path": str(work / "d.pkl")})
        raw = e.estimate_causal_effect

        def rounded(action, context):
            # Forest fits differ at ~1e-12 between processes; that float is embedded in the tool text the LLM reads, which
            # changes the request key and breaks replay. Cents are far below any decision-relevant precision (values ~1e4).
            r = raw(action, context)
            return {**r, "estimated_long_term_value": round(r["estimated_long_term_value"], 2)}
        e.estimate_causal_effect = rounded
        return e
    b.CausalEngineV6 = engine

    orig_sim = b.EcommerceSimulatorV5
    b.EcommerceSimulatorV5 = lambda **k: orig_sim(**{**k, "seed": a.sim_seed if k.get("seed") == 42 else k.get("seed")})

    errors = []                                  # upstream swallows per-week exceptions into no-ops and only prints them
    orig_write = b.tqdm.write
    def watch(msg, *args, **kw):
        if "[ERROR]" in str(msg) or "[WARNING]" in str(msg):
            errors.append(str(msg))
        return orig_write(msg, *args, **kw)
    b.tqdm.write = staticmethod(watch)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    before = ledger.spent(ITEM)
    print(f"mode={orr.mode()} model={orr.MODEL} weeks={weeks} tag={tag}")
    for bias in a.biases.split(","):
        for agent in a.agents.split(","):
            t = time.time()
            os.environ["SANDBOX_RUN_TAG"] = run_tag = f"rc2_{tag}_s{a.sim_seed}_{agent}_{bias}"
            s0, n0 = ledger.spent(ITEM), len(ledger.entries())
            df = b.run_agent_scenario(agent, bias, GOALS[bias])
            mine = [e for e in ledger.entries()[n0:] if e["item"] == ITEM and e.get("note") == run_tag]
            calls, run_cost = len(mine), sum(e["cost_usd"] for e in mine)
            if errors or calls < weeks:        # a swallowed exception = a silent no-op week; never accept that as a result
                sys.exit(f"ABORT: {agent}/{bias}: {len(errors)} swallowed errors {errors[:2]}, {calls} LLM calls for {weeks} weeks "
                         f"(rerun in record mode resumes from the cache)")
            df.to_csv(out / f"rc2_{tag}_s{a.sim_seed}_{agent}_{bias}.csv", index=False)
            print(f"RESULT {agent:13s} {bias:9s} profit={df.profit.sum():>10,.0f} trust={df.brand_trust.iloc[-1]:.3f} "
                  f"price_path={[round(x) for x in df.price]}  calls={calls} cost=${run_cost:.4f} {time.time() - t:.0f}s")
    print(f"TOTAL live spend this run: ${ledger.spent(ITEM) - before:.4f}")


if __name__ == "__main__":
    main()
