"""`reward(result, baseline)`: paired lift, floor gate, cost — the one number (well, four) the
learner stub optimises. Takes `gpc.score.summarize()` output directly (never `SimResult` or raw
traces) so it has no dependency on how a result was produced — `harness_eval/run_matrix.py`
already computes everything this needs per row; this module is the reusable, s2-owned version of
that same arithmetic, for `learner_stub.py` to call without importing `harness_eval` (which
`harness/` must never do — see `tests/harness/test_rules.py`).
"""

from __future__ import annotations


def pair_reward(result_summary: dict, baseline_summary: dict, usage: dict | None = None) -> dict:
    """One world's paired comparison. `usage` (from `harness.llm.meter.usage_of`, or a trace's
    own `usage` field) is optional — a cost-free arm has none."""
    base_offtake = baseline_summary["offtake_inr_per_day"]
    lift_pct = (result_summary["offtake_inr_per_day"] / base_offtake - 1) * 100 if base_offtake else 0.0
    return {
        "lift_pct": round(lift_pct, 4),
        "floor_met": bool(result_summary["roas_constraint_met"]),
        "cost_usd": round((usage or {}).get("cost_usd", 0.0), 4),
    }


def aggregate_reward(pairs: list[dict]) -> dict:
    """Across worlds (seeds/scenarios) for one arm. `score` is `None` when any world in the group
    missed its floor — mirrors `gpc.score.compare`'s own `score = ... if roas_constraint_met else
    None` convention, so an arm that lifts offtake by breaking the floor on even one world can't
    look good by averaging over the ones where it didn't."""
    if not pairs:
        return {"n": 0, "mean_lift_pct": 0.0, "p_lift_negative": 0.0, "floor_met_share": 0.0,
               "total_cost_usd": 0.0, "score": None}
    lifts = [p["lift_pct"] for p in pairs]
    floor_met_share = sum(p["floor_met"] for p in pairs) / len(pairs)
    mean_lift = sum(lifts) / len(lifts)
    return {
        "n": len(pairs),
        "mean_lift_pct": round(mean_lift, 4),
        "p_lift_negative": round(sum(1 for l in lifts if l < 0) / len(lifts), 4),
        "floor_met_share": round(floor_met_share, 4),
        "total_cost_usd": round(sum(p["cost_usd"] for p in pairs), 4),
        "score": round(mean_lift, 4) if floor_met_share >= 0.999 else None,
    }
