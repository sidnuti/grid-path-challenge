"""R-M1/R-M3 runner: run an upstream MoHOLLM config (partitioned or global) with the LLM routed through OpenRouter.

    SANDBOX_LLM_MODE=record uv run python runs/r_m1.py --config Penicillin/MOHOLLM-Penicillin-Context-Gemini.json --pilot
Upstream is imported, never edited; results go to runs/work/<tag>/ (upstream writes ./results relative to cwd).
"""
import argparse
import json
import os
import random
import sys
import time
import warnings
from pathlib import Path

if os.environ.get("PYTHONHASHSEED") != "0":      # upstream orders candidates via list(set(str)); needs a fixed hash seed to replay
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable] + sys.argv)

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE / "upstream"), str(HERE.parent)]
warnings.filterwarnings("ignore")

import numpy as np                                   # noqa: E402
from common import ledger, openrouter as orr         # noqa: E402
from adapters import ledger_hook                     # noqa: E402

ITEMS = {"qwen/qwen3.7-flash": "mohollm_qwen", "minimax/minimax-m3": "mohollm_minimax"}
MAX_TOKENS = 12000        # reasoning model: thinking tokens count; upstream passes 2000/5000 unless llm_settings overrides


def run(config_rel, trials, seed, salt, tag, out_root, model):
    ITEM = ITEMS[model]
    work = Path(out_root) / tag
    work.mkdir(parents=True, exist_ok=True)
    tpl = work / "prompt_templates"
    if not tpl.exists():
        tpl.symlink_to(HERE / "upstream" / "prompt_templates")
    os.chdir(work)

    os.environ["SANDBOX_RUN_TAG"] = tag          # attributes every ledger line to this run (runs share one ledger item)
    ledger_hook.install(ITEM, salt=salt)
    from benchmark_initialization import get_benchmark_fn
    from mohollm.builder import Builder
    cfg = ledger_hook.overlay(json.load(open(HERE / "upstream" / "configurations" / config_rel)), model)
    cfg["llm_settings"]["max_number_of_tokens"] = MAX_TOKENS
    if trials is not None:                       # otherwise keep the shipped config's n_trials (global 13, partitioned 15)
        cfg["n_trials"] = trials
        if "total_trials" in cfg:
            cfg["total_trials"] = trials
    cfg["seed"] = seed
    random.seed(seed)
    np.random.seed(seed)

    n0, s0, t0 = len(ledger.entries()), ledger.spent(ITEM), time.time()
    opt = Builder(config=cfg, benchmark=get_benchmark_fn(cfg)).build()
    opt.optimize()
    st = opt.statistics
    calls = [e for e in ledger.entries()[n0:] if e["item"] == ITEM and e.get("note") == tag]
    F = np.array([[v for v in f.values()] for f in st.observed_fvals])
    return dict(config=config_rel, method=cfg["optimization_method"], trials=trials, seed=seed, n_obs=len(F),
                llm_calls=len(calls), live_calls=sum(not e["cached"] for e in calls),
                trials_run=cfg["n_trials"], tokens_in=sum(e["tokens_in"] for e in calls), tokens_out=sum(e["tokens_out"] for e in calls),
                cost=sum(e["cost_usd"] for e in calls), secs=time.time() - t0, fvals=F.tolist(), configs=st.observed_configs)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="path under upstream/configurations/")
    ap.add_argument("--pilot", action="store_true", help="2 trials")
    ap.add_argument("--trials", type=int, default=None)
    ap.add_argument("--model", default="qwen/qwen3.7-flash", choices=list(ITEMS))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--salt", default=None)
    ap.add_argument("--out", default=str(HERE / "runs" / "work"))
    a = ap.parse_args()
    a.out = str(Path(a.out).resolve())      # run() chdirs into the work dir
    trials = 2 if a.pilot else a.trials
    salt = a.salt or f"s{a.seed}"
    rz = os.environ.get("SANDBOX_REASONING", "default")
    mtag = "" if a.model == "minimax/minimax-m3" else "_" + a.model.split("/")[1]
    tag = f"{'pilot' if a.pilot else 'full'}_{Path(a.config).stem}_{salt}{mtag}" + ("" if rz == "default" else f"_rz-{rz}")
    r = run(a.config, trials, a.seed, salt, tag, a.out, a.model)
    Path(a.out, tag, "result.json").write_text(json.dumps(r, indent=1))
    print("RESULT", {k: v for k, v in r.items() if k not in ("fvals", "configs")})
    print("OBS F:", np.round(np.array(r["fvals"]), 2).tolist())
