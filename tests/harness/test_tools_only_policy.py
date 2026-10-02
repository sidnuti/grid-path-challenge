"""M1 gate (handoff notes): HTNToolsOnly must meet the ROAS floor and not fall back to the
baseline due to an exception, across the dev seed and the search seeds. Slow (full 6-run sims);
run with `make harness-test-slow` or `pytest -m slow`.
"""

from __future__ import annotations

import pytest

from gpc.runner import simulate
from gpc.score import summarize
from gpc.world import build_world

from harness.policy import HTNToolsOnly

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("seed", [7, 11, 23, 42])
def test_floor_met_and_no_fallback(seed):
    policy = HTNToolsOnly()
    res = simulate(build_world(seed), policy, verbose=False)
    summary = summarize(res)
    assert summary["roas_constraint_met"], summary
    for r in res.runs:
        trace = r["trace"] or {}
        assert "fallback_reason" not in trace, f"seed {seed} run {r['run']} fell back: {trace}"


@pytest.mark.parametrize("seed", [7, 11, 23, 42])
def test_blocked_share_is_low(seed):
    """E10: the baseline blocks ~15% of what it proposes. HTNToolsOnly's precheck should keep
    the ratio of shipped/proposed close to 1 (it only proposes what should pass)."""
    policy = HTNToolsOnly()
    res = simulate(build_world(seed), policy, verbose=False)
    proposed = sum(len(r["proposed"]) for r in res.runs)
    shipped = sum(len(r["final"]) for r in res.runs)
    if proposed:
        assert shipped / proposed >= 0.90
