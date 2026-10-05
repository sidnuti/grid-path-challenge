"""The Track-A black box f(x) = ScorerV2(simulate(world_seed, decode(x))) (design/04 §2.3), with a disk cache.

    bb = BlackBox("sc1_cannibal", seed=7)            # E1 encoding (10-d)
    r = bb(x)                                        # dict: inc_rev, spend, iroas, f2, f3, constraints, ...

Deterministic per (scenario, seed, x): common random numbers, and the decoder is pure. Results are cached as
JSON lines under `runs/cache/bb/<scenario>_s<seed>_<enc>.jsonl`, keyed by x rounded to 12 decimals plus
CODE_VERSION (bump it whenever simulator, decoder or goal code changes meaning).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from gpc.world import WARMUP_DAYS, build_world

from .decode import Encoding, decode, warmup_spend_per_day
from .goals import measure
from .sim import WarmStart, run

CODE_VERSION = "p3.2"
CACHE_DIR = Path(os.environ.get("BENCH_CACHE", Path(__file__).resolve().parents[1] / "runs" / "cache" / "bb"))


def x_key(x) -> str:
    return hashlib.sha256((CODE_VERSION + "|" + ",".join(f"{v:.12f}" for v in np.asarray(x, float))).encode()).hexdigest()[:20]


class BlackBox:
    def __init__(self, scenario: str, seed: int, enc: Encoding = Encoding(), cache: bool = True):
        self.scenario, self.seed, self.enc = scenario, seed, enc
        self.world = build_world(seed, scenario)
        self._ws = None
        self.cache = cache
        # one cache file per process (parallel arms append concurrently); all of a problem's files are read
        stem = f"{scenario}_s{seed}_{'b' if enc.budget_scale else 'e1'}"
        self.path = CACHE_DIR / f"{stem}.{os.getpid()}.jsonl"
        self._mem: dict[str, dict] = {}
        if cache and CACHE_DIR.exists():
            for f in sorted(CACHE_DIR.glob(f"{stem}.*.jsonl")):
                for line in f.read_text().splitlines():
                    if line.strip():
                        r = json.loads(line)
                        self._mem[r["key"]] = r
        self.n_evals = 0          # evaluations served (cache hits included)
        self.n_sims = 0           # evaluations actually simulated

    @property
    def ws(self) -> WarmStart:
        if self._ws is None:
            self._ws = WarmStart(self.world)
        return self._ws

    def budget_per_day(self) -> float:
        """B per day = warm-up spend per day (design/03 §1 F1: B = warm-up spend × 6 weeks)."""
        return float(pd.concat(self.ws.acc["daily_facts"]).spend_inr.sum() / WARMUP_DAYS)

    def __call__(self, x) -> dict:
        x = np.clip(np.asarray(x, float), 0.0, 1.0)
        k = x_key(x)
        self.n_evals += 1
        if k in self._mem:
            return self._mem[k]
        t0 = time.time()
        res = run(self.ws, lambda obs: decode(x, obs, self.enc))
        out = measure(self.world, res, self.budget_per_day())
        out.update({"key": k, "x": [float(v) for v in x], "secs": round(time.time() - t0, 2)})
        out = json.loads(json.dumps(out, default=float))          # plain JSON types (cache = what callers see)
        self._mem[k] = out
        self.n_sims += 1
        if self.cache:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as fh:
                fh.write(json.dumps(out) + "\n")
        return out
