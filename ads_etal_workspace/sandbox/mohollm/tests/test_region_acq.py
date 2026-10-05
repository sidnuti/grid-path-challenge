"""region_acquisition_functions/score_region_acq_hv.py (ScoreRegionHVC) and schedulers."""
import numpy as np
import pytest

from helpers import hv2d, make_partitioner
from mohollm.region_acquisition_functions.score_region_acq_hv import ScoreRegionHVC
from mohollm.schedulers.cosine_annealing_scheduler import CosineAnnealingScheduler

pytestmark = pytest.mark.offline

BOX = {"x0": [0.0, 1.0], "x1": [0.0, 1.0]}


class FixedScheduler:
    def __init__(self, v):
        self.v = v

    def get_value(self):
        return self.v


def setup(n=60, seed=0, alpha=0.5, scheduler=None, m0=5):
    kd, pts, fv, st = make_partitioner(n, BOX, BOX.keys(), m0=m0, seed=seed)
    regions = kd.partition(pts, fv)
    acq = ScoreRegionHVC()
    acq.metrics_targets, acq.statistics, acq.n_trials, acq.alpha, acq.scheduler = ["min", "min"], st, 15, alpha, scheduler
    return acq, regions, st


def capture(monkeypatch, acq):
    """Record every softmax-norm input (exploitation, var, ucb, volume, in call order) and the sampling distribution p."""
    calls, chosen = [], {}
    orig = acq.norm
    monkeypatch.setattr(acq, "norm", lambda x: (calls.append(np.array(x)), orig(x))[1])

    def fake_choice(a, size=None, replace=True, p=None):
        chosen["p"] = np.array(p)
        return np.arange(size)
    monkeypatch.setattr(np.random, "choice", fake_choice)
    return calls, chosen


def normalized(fvals):
    a = np.array([[f["F1"], f["F2"]] for f in fvals])
    return (a - a.min(0)) / (a.max(0) - a.min(0) + 1e-5)


def test_hv_contribution_equals_independent_brute_force():
    acq, regions, st = setup()
    nf = normalized(st.observed_fvals)
    ref = (1.2, 1.2)
    total = hv2d(nf, ref)
    for r in regions:
        got = acq.compute_hypervolume_contribution(r.points_indices, nf, 2)
        want = [total - hv2d(np.delete(nf, i, axis=0), ref) for i in r.points_indices]
        np.testing.assert_allclose(got, want, atol=1e-9)
        assert all(g >= -1e-12 for g in got)                 # removing a point never increases HV


def test_dominated_point_has_zero_contribution():
    acq, regions, st = setup(n=30)
    nf = normalized(st.observed_fvals)
    nf[0] = nf.max(0) * 0.999 + 0.001          # dominated by anything better in both objectives
    c = acq.compute_hypervolume_contribution([0], nf, 2)[0]
    assert c == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("alpha", [0.0, 0.01, 0.5, 1.0, 1.5])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_probabilities_are_nonnegative_and_sum_to_one(monkeypatch, alpha, seed):
    acq, regions, _ = setup(seed=seed, alpha=alpha)
    assert len(regions) > 3
    calls, chosen = capture(monkeypatch, acq)
    acq.select_regions(regions, 3)
    p = chosen["p"]
    assert (p >= 0).all() and p.sum() == pytest.approx(1.0) and len(p) == len(regions)


def test_exploitation_term_is_max_contribution_per_box(monkeypatch):
    """Pins the behaviour documented in report 04 §6: mu = MAX hv-contribution in the box (not the mean)."""
    acq, regions, st = setup()
    calls, _ = capture(monkeypatch, acq)
    acq.select_regions(regions, 3)
    nf = normalized(st.observed_fvals)
    total = hv2d(nf, (1.2, 1.2))
    expected = [max(total - hv2d(np.delete(nf, i, axis=0), (1.2, 1.2)) for i in r.points_indices) for r in regions]
    np.testing.assert_allclose(calls[0], expected, atol=1e-9)
    mean_based = [np.mean([total - hv2d(np.delete(nf, i, axis=0), (1.2, 1.2)) for i in r.points_indices]) for r in regions]
    assert not np.allclose(calls[0], mean_based)             # i.e. the test can distinguish max from mean


def test_score_formula_and_alpha_comes_from_scheduler(monkeypatch):
    acq, regions, _ = setup(alpha=0.5, scheduler=FixedScheduler(0.123))
    calls, chosen = capture(monkeypatch, acq)
    acq.select_regions(regions, 3)
    e, _, m, v = [__import__("scipy.special", fromlist=["softmax"]).softmax(c) for c in calls]   # order: exploit, var, ucb, volume
    scores = e + 0.123 * (0.5 * v + 0.5 * m)
    np.testing.assert_allclose(chosen["p"], scores / scores.sum(), atol=1e-12)
    assert 0.123 != acq.alpha                                 # the scheduler's value overrode the static alpha


def test_returns_all_regions_when_request_exceeds_available():
    acq, regions, _ = setup()
    assert acq.select_regions(regions, len(regions) + 5) == regions


def test_selection_is_without_replacement_and_seeded():
    acq, regions, _ = setup()
    np.random.seed(0)
    a = acq.select_regions(regions, 4)
    np.random.seed(0)
    b = acq.select_regions(regions, 4)
    assert len(a) == 4 and len({id(r) for r in a}) == 4 and [id(r) for r in a] == [id(r) for r in b]


def test_single_objective_is_rejected():
    acq, regions, _ = setup()
    acq.metrics_targets = ["min"]
    with pytest.raises(ValueError):
        acq.select_regions(regions, 2)


def test_higher_exploitation_gets_higher_probability_at_alpha_zero(monkeypatch):
    acq, regions, _ = setup(alpha=0.0)
    calls, chosen = capture(monkeypatch, acq)
    acq.select_regions(regions, 3)
    order_e, order_p = np.argsort(calls[0]), np.argsort(chosen["p"])
    assert list(order_e) == list(order_p) or np.allclose(np.sort(chosen["p"]), chosen["p"][order_e])


# ---- schedulers ---------------------------------------------------------------------------------------------------
def test_cosine_annealing_scheduler_is_a_valid_alpha_schedule():
    """The only scheduler the paper configs use (COSINE_ANNEALING, alpha in [0.01, 1.0]); starts at alpha_max, decays."""
    s = CosineAnnealingScheduler()
    s.apply_settings({"alpha_min": 0.01, "alpha_max": 1.0, "restart_interval": 100})
    vals = [s.get_value() for _ in range(100)]
    assert all(0.01 - 1e-9 <= v <= 1.0 + 1e-9 for v in vals)
    assert vals[0] == pytest.approx(1.0) and vals[-1] < vals[0]
    assert all(a >= b - 1e-12 for a, b in zip(vals, vals[1:]))


@pytest.mark.parametrize("name,settings", [
    ("CONSTANT_SCHEDULER", {"value": 0.3}),
    ("LINEAR_DECAY_SCHEDULER", {"initial_samples": 1.0, "decay_rate": 0.05}),
    ("COSINE_DECAY_SCHEDULER", {"initial_samples": 1.0, "min_samples": 0.0, "total_steps": 10}),
])
def test_finding_several_upstream_schedulers_cannot_be_configured(name, settings):
    """UPSTREAM DEFECT: these schedulers (copied from a sample-count scheduler family) raise on apply_settings, so only
    COSINE_ANNEALING / EPSILON_DECAY are usable as a region-alpha schedule. Not exercised by the paper's configs."""
    from mohollm.settings import SCHEDULERS
    with pytest.raises((AttributeError, KeyError)):
        SCHEDULERS[name].apply_settings({"scheduler": name, **settings})
        SCHEDULERS[name].get_value()          # CONSTANT configures but then fails here (n_samples is never set)


def test_finding_epsilon_decay_scheduler_returns_sample_counts_not_alpha():
    from mohollm.settings import SCHEDULERS
    s = SCHEDULERS["EPSILON_DECAY_SCHEDULER"]
    s.apply_settings({"scheduler": "EPSILON_DECAY_SCHEDULER"})
    assert s.get_value() > 10                                 # default initial_value=100 -> not a [0, 1] alpha
