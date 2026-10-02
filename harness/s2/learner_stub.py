"""`propose_params`: the interface a real learner will implement. The stub here is deliberately
dumb — "best mean arm among the ones that held the floor everywhere" — so that swapping it for
something smarter later (a bandit, a small model fit on traces) is a drop-in replacement behind
the same `propose_params(arm_rewards, registry, base_params) -> Params` signature, not a rewrite
of whatever calls it.

CLI (for a cron job): reads a JSON file of `{arm_name: aggregate_reward_dict}` — the shape
`harness.s2.reward.aggregate_reward` returns, one entry per arm, typically produced by running
`harness_eval/run_matrix.py`-style sweeps where each "arm" is actually an S2 `Arm` (not a policy
arm — building that sweep is future work; this CLI's job starts at "given the rewards, which arm
wins", not at collecting them) — and writes the chosen `Params` to a file `PARAMS_PATH` can read.

    python -m harness.s2.learner_stub --rewards rewards.json --out harness/params/learned.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..config import Params, load_params
from .arms import ArmRegistry


def propose_params(arm_rewards: dict[str, dict], registry: ArmRegistry, base_params: Params,
                   require_floor_met: bool = True) -> tuple[Params, str]:
    """Returns (params, chosen_arm_name). Among arms registry knows about *and* that appear in
    `arm_rewards`: prefer the ones with `floor_met_share >= 0.999` and `score is not None`; if
    none qualify, fall back to the best `mean_lift_pct` regardless (better than refusing to
    propose anything, but the caller should treat that case as "no safe winner yet")."""
    known = {name: r for name, r in arm_rewards.items() if name in registry}
    if not known:
        return base_params, "baseline_default" if "baseline_default" in registry else next(iter(registry.names()), "")
    qualified = {n: r for n, r in known.items() if not require_floor_met or r.get("score") is not None}
    pool = qualified or known
    best_name = max(pool, key=lambda n: pool[n].get("mean_lift_pct", float("-inf")))
    return registry.materialize(best_name, base_params), best_name


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rewards", required=True, help="JSON file: {arm_name: aggregate_reward dict}")
    ap.add_argument("--base-params", default=None, help="defaults to harness/params/default.json")
    ap.add_argument("--out", default="harness/params/learned.json")
    ap.add_argument("--allow-floor-miss", action="store_true",
                   help="propose the best arm even if none held the floor on every world")
    a = ap.parse_args()
    rewards = json.loads(Path(a.rewards).read_text())
    base = load_params(a.base_params)
    registry = ArmRegistry()
    params, chosen = propose_params(rewards, registry, base, require_floor_met=not a.allow_floor_miss)
    Path(a.out).write_text(json.dumps(params.to_dict(), indent=2))
    print(f"chose arm {chosen!r}; wrote {a.out}")


if __name__ == "__main__":
    main()
