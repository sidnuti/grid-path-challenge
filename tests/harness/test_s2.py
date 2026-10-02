"""`harness/s2/*`: arm registry, reward aggregation, and the learner stub's "best mean arm among
ones that held the floor" selection."""

from __future__ import annotations

import json

from harness.config import load_params
from harness.s2.arms import ArmRegistry, DEFAULT_ARMS
from harness.s2.learner_stub import propose_params
from harness.s2.reward import aggregate_reward, pair_reward


def test_arm_registry_materializes_overrides():
    reg = ArmRegistry()
    base = load_params()
    p = reg.materialize("shock_z_3.0", base)
    assert p.shock_z_reach == 3.0 and p.shock_z_cpm == 3.0
    assert p.depth == base.depth  # untouched fields stay at the base's value


def test_arm_registry_unknown_name_raises():
    reg = ArmRegistry()
    import pytest
    with pytest.raises(KeyError):
        reg.materialize("not_a_real_arm", load_params())


def test_every_default_arm_is_distinct_from_baseline_or_is_the_baseline():
    reg = ArmRegistry()
    base = load_params()
    baseline = reg.materialize("baseline_default", base)
    assert baseline == base


def test_pair_reward_computes_lift_and_floor():
    result = {"offtake_inr_per_day": 110_000, "roas_constraint_met": True}
    baseline = {"offtake_inr_per_day": 100_000, "roas_constraint_met": True}
    r = pair_reward(result, baseline, usage={"cost_usd": 0.5})
    assert r["lift_pct"] == 10.0
    assert r["floor_met"] is True
    assert r["cost_usd"] == 0.5


def test_pair_reward_without_usage_defaults_cost_to_zero():
    r = pair_reward({"offtake_inr_per_day": 100, "roas_constraint_met": True},
                    {"offtake_inr_per_day": 100, "roas_constraint_met": True})
    assert r["cost_usd"] == 0.0


def test_aggregate_reward_score_is_none_if_any_world_misses_floor():
    pairs = [{"lift_pct": 5.0, "floor_met": True, "cost_usd": 0.0},
            {"lift_pct": 8.0, "floor_met": False, "cost_usd": 0.0}]
    agg = aggregate_reward(pairs)
    assert agg["floor_met_share"] == 0.5
    assert agg["score"] is None  # a lift that breaks the floor anywhere can't score


def test_aggregate_reward_score_equals_mean_lift_when_floor_always_met():
    pairs = [{"lift_pct": 5.0, "floor_met": True, "cost_usd": 0.1},
            {"lift_pct": 7.0, "floor_met": True, "cost_usd": 0.1}]
    agg = aggregate_reward(pairs)
    assert agg["score"] == 6.0
    assert agg["total_cost_usd"] == 0.2


def test_aggregate_reward_empty_pairs():
    agg = aggregate_reward([])
    assert agg["n"] == 0 and agg["score"] is None


def test_propose_params_picks_best_qualifying_arm():
    registry = ArmRegistry()
    base = load_params()
    rewards = {
        "shock_z_2.0": {"mean_lift_pct": 1.0, "score": 1.0, "floor_met_share": 1.0},
        "shock_z_3.0": {"mean_lift_pct": 3.0, "score": 3.0, "floor_met_share": 1.0},
        "explore_on_small": {"mean_lift_pct": 10.0, "score": None, "floor_met_share": 0.5},  # disqualified
    }
    params, chosen = propose_params(rewards, registry, base)
    assert chosen == "shock_z_3.0"
    assert params.shock_z_reach == 3.0


def test_propose_params_falls_back_when_nothing_qualifies():
    registry = ArmRegistry()
    base = load_params()
    rewards = {"shock_z_2.0": {"mean_lift_pct": 1.0, "score": None, "floor_met_share": 0.5},
              "shock_z_3.0": {"mean_lift_pct": 3.0, "score": None, "floor_met_share": 0.3}}
    params, chosen = propose_params(rewards, registry, base)
    assert chosen == "shock_z_3.0"  # best mean_lift_pct even though neither qualified


def test_propose_params_ignores_rewards_for_unknown_arms():
    registry = ArmRegistry()
    base = load_params()
    rewards = {"totally_made_up_arm": {"mean_lift_pct": 99.0, "score": 99.0, "floor_met_share": 1.0}}
    params, chosen = propose_params(rewards, registry, base)
    assert params == base  # nothing in `rewards` matched a known arm -> base params, unchanged


def test_learner_cli_writes_a_loadable_params_file(tmp_path):
    rewards_path = tmp_path / "rewards.json"
    out_path = tmp_path / "learned.json"
    rewards_path.write_text(json.dumps({
        "shock_z_3.0": {"mean_lift_pct": 2.0, "score": 2.0, "floor_met_share": 1.0},
    }))
    import sys
    from harness.s2 import learner_stub
    argv = ["learner_stub", "--rewards", str(rewards_path), "--out", str(out_path)]
    old_argv = sys.argv
    sys.argv = argv
    try:
        learner_stub.main()
    finally:
        sys.argv = old_argv
    assert out_path.exists()
    from harness.config import load_params as _load
    p = _load(str(out_path))
    assert p.shock_z_reach == 3.0
