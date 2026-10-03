"""`harness/tools/sizing.py::select_raises`. No unit tests existed for this module before
2026-10-03 — the only coverage was indirect, through the M1 gate's floor/lift checks, which can't
tell a correctly-sized raise set from one that blew through its allowance by 100x and got trimmed
back down anyway by `gpc.guardrails`' G8 portfolio floor. That's exactly what was happening (see
the module docstring's account of the bug); these tests exist so a regression here is caught at
the unit level, not only inferred later from a lift number that still happens to look fine.
"""

from __future__ import annotations

import pandas as pd
import pytest

from harness.config import load_params
from harness.tools.sizing import select_raises


def _raise(campaign_id, keyword_id, delta_spend, delta_rev, iota=1.0):
    return {"campaign_id": campaign_id, "keyword_id": keyword_id, "action_type": "increase_cpm",
           "current_value": 100.0, "new_value": 150.0, "iota": iota,
           "pred_delta_spend": delta_spend, "pred_delta_rev": delta_rev, "reason": "test"}


def test_select_raises_never_exceeds_the_allowance():
    """The headline regression: every candidate here is individually profitable (ratio > 1), and
    their combined delta_spend (figures mirroring the real seed-23/run-2 overshoot this test is
    modelled on) is >100x a small allowance. The old code shipped all of them; the allowance must
    now actually bound the total."""
    raises = pd.DataFrame([
        _raise("C-S4-DEL", "", 107.25, 1429.27, 0.594),
        _raise("C-S3-DEL", "K02", 31.18, 523.67, 0.428),
        _raise("C-S1-PUN", "", 57.20, 461.26, 0.846),
        _raise("C-S4-HYD", "K06", 66.22, 642.80, 0.552),
        _raise("C-S1-DEL", "", 500.00, 2584.97, 0.797),
    ])
    params = load_params()
    selected = select_raises(raises, allowance_inr_day=43.83, params=params)
    assert selected.pred_delta_spend.sum() <= 43.83 + 1e-6


def test_select_raises_picks_highest_ratio_first_under_a_binding_allowance():
    raises = pd.DataFrame([
        _raise("C-A", "", 100.0, 150.0, 1.0),   # ratio 1.5
        _raise("C-B", "", 100.0, 500.0, 1.0),   # ratio 5.0 -- should win when only one fits
    ])
    params = load_params()
    selected = select_raises(raises, allowance_inr_day=150.0, params=params)
    assert set(selected.campaign_id) == {"C-B"}


def test_select_raises_takes_everything_when_allowance_is_ample():
    raises = pd.DataFrame([_raise("C-A", "", 50.0, 100.0), _raise("C-B", "", 50.0, 80.0)])
    params = load_params()
    selected = select_raises(raises, allowance_inr_day=1000.0, params=params)
    assert len(selected) == 2
    assert selected.pred_delta_spend.sum() == 100.0


def test_select_raises_empty_allowance_selects_nothing():
    raises = pd.DataFrame([_raise("C-A", "", 50.0, 100.0)])
    params = load_params()
    assert len(select_raises(raises, allowance_inr_day=0.0, params=params)) == 0
    assert len(select_raises(raises, allowance_inr_day=-5.0, params=params)) == 0


def test_select_raises_empty_candidates():
    params = load_params()
    out = select_raises(pd.DataFrame(columns=["campaign_id", "keyword_id", "action_type",
                                              "pred_delta_spend", "pred_delta_rev", "iota"]),
                        allowance_inr_day=100.0, params=params)
    assert len(out) == 0


def test_select_raises_drops_non_positive_ratio_candidates():
    """A candidate with iota=0 (fully cannibalised) or delta_rev <= 0 contributes zero or
    negative offtake value and must never be picked, however much allowance is free."""
    raises = pd.DataFrame([_raise("C-A", "", 50.0, 100.0, iota=0.0),
                          _raise("C-B", "", 50.0, -10.0, iota=1.0)])
    params = load_params()
    selected = select_raises(raises, allowance_inr_day=1000.0, params=params)
    assert len(selected) == 0


def test_select_raises_drops_non_positive_spend_candidates():
    """The old `pred_delta_spend > 1` screen (a no-raise/no-op candidate, e.g. a chosen_bid equal
    to the live bid passed through by mistake) is preserved."""
    raises = pd.DataFrame([_raise("C-A", "", 0.5, 100.0)])
    params = load_params()
    selected = select_raises(raises, allowance_inr_day=1000.0, params=params)
    assert len(selected) == 0


def test_select_raises_never_exceeds_allowance_property(monkeypatch):
    """Property-style check across a spread of random candidate sets and allowances — the one
    invariant that must always hold, regardless of how candidates are shaped."""
    import numpy as np
    rng = np.random.default_rng(0)
    params = load_params()
    for trial in range(25):
        n = rng.integers(1, 15)
        raises = pd.DataFrame([
            _raise(f"C-{i}", "", float(rng.uniform(1, 500)), float(rng.uniform(-50, 2000)),
                  float(rng.uniform(0, 1)))
            for i in range(n)
        ])
        allowance = float(rng.uniform(0, 1000))
        selected = select_raises(raises, allowance_inr_day=allowance, params=params)
        assert selected.pred_delta_spend.sum() <= allowance + 1e-6, (trial, allowance)
