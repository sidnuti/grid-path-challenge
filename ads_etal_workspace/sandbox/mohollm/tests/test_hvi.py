"""acquisition_functions/hypervolume_improvement.py: top-k ordering equals brute-force HVI on toy fronts."""
import numpy as np
import pytest

from helpers import hv2d
from mohollm.acquisition_functions.hypervolume_improvement import HypervolumeImprovement
from mohollm.statistics.statistics import Statistics

pytestmark = pytest.mark.offline


def acq_with(observed):
    st = Statistics()
    st.observed_fvals = [{"F1": a, "F2": b} for a, b in observed]
    h = HypervolumeImprovement()
    h.statistics, h.metrics_targets = st, ["min", "min"]
    return h


def brute_force_hvi(observed, cands):
    allp = np.vstack([observed, cands])
    lo, hi = allp.min(0), allp.max(0)
    norm = lambda a: (np.asarray(a) - lo) / (hi - lo + 1e-5)
    ref = (1.2, 1.2)
    base = hv2d(norm(observed), ref)
    return [hv2d(norm(np.vstack([observed, c])), ref) - base for c in cands]


@pytest.mark.parametrize("seed", range(8))
def test_contributions_and_topk_order_match_brute_force(seed):
    rng = np.random.default_rng(seed)
    obs = rng.uniform(0.2, 1.0, (8, 2))
    cands = rng.uniform(0.0, 1.0, (12, 2))
    h = acq_with(obs)
    idx, evals, contrib = h.select_candidate_point([{"F1": a, "F2": b} for a, b in cands], top_k=4)
    want = brute_force_hvi(obs, cands)
    np.testing.assert_allclose(contrib, want, atol=1e-9)
    assert list(idx) == list(np.argsort(want)[::-1][:4])
    assert [e for e in evals] == [{"F1": cands[i][0], "F2": cands[i][1]} for i in idx]


def test_dominated_candidate_has_zero_improvement():
    obs = np.array([[0.2, 0.8], [0.8, 0.2], [0.5, 0.5]])
    h = acq_with(obs)
    _, _, c = h.select_candidate_point([{"F1": 0.9, "F2": 0.9}, {"F1": 0.1, "F2": 0.1}], top_k=1)
    assert c[0] == pytest.approx(0.0, abs=1e-9) and c[1] > 0.0


def test_default_returns_single_best():
    obs = np.array([[0.5, 0.5]])
    h = acq_with(obs)
    idx, evals, _ = h.select_candidate_point([{"F1": 0.4, "F2": 0.6}, {"F1": 0.1, "F2": 0.1}])
    assert list(idx) == [1] and len(evals) == 1


def test_multiple_evaluations_per_candidate_are_averaged_first():
    obs = np.array([[0.5, 0.5]])
    h = acq_with(obs)
    cand = [[{"F1": "0.2", "F2": 0.4}, {"F1": 0.4, "F2": "0.2"}], {"F1": 0.9, "F2": 0.9}]   # strings and dicts both occur upstream
    avg = h._calculate_average_evaluation(cand)
    assert avg[0] == pytest.approx({"F1": 0.3, "F2": 0.3}) and avg[1] == {"F1": 0.9, "F2": 0.9}
