"""Smoke tests for `harness_eval/` (M4 offline tooling — never imported by `harness/` itself, so
these live outside `tests/harness/` and are not subject to that AST rule scan). Named
`test_harness_eval.py`, a flat file rather than a `tests/harness_eval/` package, on purpose: a
`tests/harness/` subpackage once shadowed the real `harness` package in pytest's import
resolution (see the build log's M0 entry) — `tests/harness_eval/` would collide with
`harness_eval` the same way, and a flat file sidesteps it entirely.
"""

from __future__ import annotations

import pandas as pd
import pytest

from harness_eval.run_matrix import LeafAblationLLM, build_arms, run_matrix
from harness_eval.worlds import HELDOUT_SEEDS, PERTURBATIONS, SEARCH_SEEDS, world_specs


def test_world_specs_covers_search_heldout_and_perturbed():
    specs = world_specs(include_perturbed=True)
    labels = {s[0] for s in specs}
    assert len(specs) == len(SEARCH_SEEDS) + len(HELDOUT_SEEDS) + len(PERTURBATIONS)
    assert {f"search_{s}" for s in SEARCH_SEEDS} <= labels
    assert {f"heldout_{s}" for s in HELDOUT_SEEDS} <= labels
    assert set(PERTURBATIONS) <= labels


def test_world_specs_without_perturbed_is_just_seeds():
    specs = world_specs(include_perturbed=False)
    assert len(specs) == len(SEARCH_SEEDS) + len(HELDOUT_SEEDS)


def test_build_arms_cost_free_only_when_llm_disabled():
    from harness.config import load_params
    arms = build_arms(load_params(), llm_enabled=False)
    assert set(arms) == {"no_op", "baseline", "tools_only"}


def test_build_arms_adds_full_and_loo_when_llm_enabled():
    from harness.config import load_params
    arms = build_arms(load_params(), llm_enabled=True)
    assert "full" in arms
    assert all(f"loo_{leaf}" in arms for leaf in ("L1_value", "L2_shock", "L3_sibling", "L4_explore", "L6_review"))


class _MockLLM:
    def complete_json(self, system, user, schema, timeout, **kwargs):
        from harness.llm.client import Usage
        return {}, Usage(calls=1)


def test_leaf_ablation_llm_blocks_only_the_named_leaf():
    mock = _MockLLM()
    ablated = LeafAblationLLM(mock, "L2_shock")
    with pytest.raises(RuntimeError):
        ablated.complete_json("s", "u", {}, 5.0, leaf="L2_shock")
    resp, usage = ablated.complete_json("s", "u", {}, 5.0, leaf="L1_value")
    assert usage.calls == 1


def test_run_matrix_cost_free_arms_on_one_world():
    df = run_matrix(world_names=["search_7"], n_replicates=1, include_perturbed=False)
    assert set(df.arm) == {"no_op", "baseline", "tools_only"}
    assert len(df) == 3
    base_row = df[df.arm == "baseline"].iloc[0]
    assert base_row.offtake_vs_baseline_pct == 0.0
    assert (df.world == "search_7").all()
