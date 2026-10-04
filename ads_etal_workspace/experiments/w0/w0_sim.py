"""W0 runner: simulate a policy with the harness at an OLD commit, from a separate git worktree.
Imports only `gpc` and `harness` (from whatever is first on PYTHONPATH), never `experiments.lib` (which needs the current harness).
Traces are dropped before pickling, because they hold old-harness objects the current code may not unpickle.

    cd w0_old_harness && PYTHONPATH=. ../grid-path-challenge/.venv/bin/python ../experiments/w0/w0_sim.py --arm l0 --seeds 7 11
"""

from __future__ import annotations

import argparse
import hashlib
import pickle
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

CACHE = Path(__file__).resolve().parents[1] / "results" / "cache"


def _one(args):
    arm, seed = args
    import harness
    from gpc.policy import DeterministicTraversal
    from gpc.runner import simulate
    from gpc.world import build_world
    from harness.policy import HTNToolsOnly
    pol = {"l0": HTNToolsOnly, "baseline": DeterministicTraversal}[arm]()
    res = simulate(build_world(seed, "dev"), pol, verbose=False)
    for r in res.runs:
        r["trace"] = None
    return arm, seed, res, str(Path(harness.__file__).resolve().parent)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="l0")
    ap.add_argument("--seeds", nargs="*", type=int, default=[7, 11, 23, 42, 101, 202])
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    CACHE.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(a.jobs) as ex:
        for arm, seed, res, hpath in ex.map(_one, [(a.arm, s) for s in a.seeds]):
            p = CACHE / f"old{commit}_{arm}__{seed}__dev__{commit}.pkl"
            p.write_bytes(pickle.dumps(res))
            print(f"{arm} seed {seed} harness from {hpath} -> {p.name}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
