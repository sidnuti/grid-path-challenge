"""Run (arm, seed) simulations in parallel into the shared cache.

    PYTHONPATH=grid-path-challenge:. python -m experiments.run_arms --seeds 7 11 23 42 101 202 --jobs 4
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

from experiments.lib.arms import FREE_ARMS, factory, llm_factory
from experiments.lib.runs import ALL_SEEDS, code_hash, run_cached


def _one(args):
    arm, seed, scenario = args
    t0 = time.time()
    run_cached(arm, llm_factory(arm, seed, scenario) if arm.startswith("llm_") else factory(arm), seed, scenario)
    return arm, seed, scenario, round(time.time() - t0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="*", default=FREE_ARMS)
    ap.add_argument("--seeds", nargs="*", type=int, default=list(ALL_SEEDS))
    ap.add_argument("--scenario", default="dev")
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    jobs = [(arm, s, a.scenario) for s in a.seeds for arm in a.arms]
    print(f"code hash {code_hash()}; {len(jobs)} simulations, {a.jobs} workers", flush=True)
    with ProcessPoolExecutor(a.jobs) as ex:
        futs = [ex.submit(_one, j) for j in jobs]
        for i, f in enumerate(as_completed(futs), 1):
            print(f"[{i}/{len(jobs)}] {f.result()}", flush=True)


if __name__ == "__main__":
    main()
