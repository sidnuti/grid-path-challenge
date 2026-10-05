"""Legacy goldens for sim v2: freeze today's simulator output so every v2 change can be checked against it.

With all v2 flags off, the three output tables and the shipped actions must match these byte for byte
(../plan/2026-10-05_sandbox_ads_e2e_plan.md, P0.4 / P1 gates).

    PYTHONPATH=. .venv/bin/python scripts/make_goldens.py            # write tests/goldens/
    PYTHONPATH=. .venv/bin/python scripts/make_goldens.py --check    # compare against them
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from gpc.policy import DeterministicTraversal, NoOpPolicy
from gpc.runner import simulate
from gpc.world import build_world

GOLD = Path(__file__).resolve().parents[1] / "tests" / "goldens"
SEEDS = (7, 11, 23, 42)
POLICIES = {"no_op": NoOpPolicy, "traversal": DeterministicTraversal}
TABLES = ("daily_facts", "campaign_daily", "sku_city_daily")


def digest(df: pd.DataFrame) -> str:
    return hashlib.sha256(df.to_csv(index=False, float_format="%.17g").encode()).hexdigest()


def run_one(seed: int, pol: str) -> dict[str, pd.DataFrame]:
    res = simulate(build_world(seed=seed), POLICIES[pol]())
    out = {t: getattr(res, t) for t in TABLES}
    out["actions"] = pd.concat([r["final"].assign(run=r["run"]) for r in res.runs], ignore_index=True)
    return out


def _job(args):
    seed, pol = args
    return seed, pol, run_one(seed, pol)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    jobs = [(s, p) for s in SEEDS for p in POLICIES]
    manifest_path = GOLD / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if a.check else {}
    bad = 0
    with ProcessPoolExecutor(max_workers=len(jobs)) as ex:
        for seed, pol, tabs in ex.map(_job, jobs):
            for name, df in tabs.items():
                key = f"s{seed}_{pol}_{name}"
                h = digest(df)
                if a.check:
                    ok = manifest.get(key) == h
                    bad += not ok
                    print(f"{'ok ' if ok else 'BAD'} {key}")
                else:
                    GOLD.mkdir(parents=True, exist_ok=True)
                    df.to_parquet(GOLD / f"{key}.parquet", index=False)
                    manifest[key] = h
    if not a.check:
        manifest_path.write_text(json.dumps(dict(sorted(manifest.items())), indent=1))
        print(f"wrote {len(manifest)} goldens to {GOLD}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
