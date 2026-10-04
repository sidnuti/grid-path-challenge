"""Run policies on worlds, with an on-disk cache so no experiment re-simulates what another already
ran. The cache key includes a hash of every harness/gpc source file, so editing the code
invalidates it automatically."""

from __future__ import annotations

import hashlib
import pickle
from pathlib import Path

from gpc.runner import simulate
from gpc.world import build_world

ROOT = Path(__file__).resolve().parents[2]
GPC_ROOT = ROOT / "grid-path-challenge"
CACHE = ROOT / "experiments" / "results" / "cache"

SEARCH_SEEDS = (7, 11, 23, 42)
HELDOUT_SEEDS = (101, 202)
ALL_SEEDS = SEARCH_SEEDS + HELDOUT_SEEDS


def code_hash() -> str:
    h = hashlib.sha256()
    for sub in ("gpc", "harness", "harness_l2p"):
        for p in sorted((GPC_ROOT / sub).rglob("*.py")):
            h.update(p.relative_to(GPC_ROOT).as_posix().encode())
            h.update(p.read_bytes())
    for p in sorted((GPC_ROOT / "harness").rglob("*.json")):
        h.update(p.read_bytes())
    for p in sorted((GPC_ROOT / "harness_l2p").rglob("*.md")):         # L2′ prompts change behaviour too
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def run_cached(arm: str, build_policy, seed: int, scenario: str = "dev", use_cache: bool = True):
    """Returns the SimResult for `arm` on (seed, scenario). `build_policy` is a zero-arg factory
    (a fresh policy per simulation)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = f"{arm}__{seed}__{Path(scenario).stem}__{code_hash()}.pkl"
    path = CACHE / key
    if use_cache and path.exists():
        return pickle.loads(path.read_bytes())
    res = simulate(build_world(seed, scenario), build_policy(), verbose=False)
    if use_cache:
        path.write_bytes(pickle.dumps(res))
    return res


def load_latest(arm: str, seed: int, scenario: str = "dev"):
    """Newest cached SimResult for (arm, seed, scenario), whatever code version made it. Returns
    (result, code_hash). Analysis scripts collect the hashes they saw and write them into their
    output, so a result computed from a mix of code versions is visible rather than silent."""
    files = sorted(CACHE.glob(f"{arm}__{seed}__{Path(scenario).stem}__*.pkl"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"no cached run for {arm} seed {seed} {scenario}; run experiments.run_arms first")
    p = files[-1]
    return pickle.loads(p.read_bytes()), p.stem.split("__")[-1]
