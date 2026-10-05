"""Benchmarks vs independent references: closed-form definitions (written here, not copied from upstream) and BoTorch's
own test functions evaluated in float64."""
import numpy as np
import pytest
import torch

from benchmark_initialization import get_benchmark_fn

pytestmark = pytest.mark.offline
rng = np.random.default_rng(0)


def bench(name, **settings):
    return get_benchmark_fn({"benchmark": name, "benchmark_settings": settings, "seed": 0,
                             "llm_settings": {"model": "x"}, "metrics": ["F1", "F2"]})


def evaluate(b, x):
    pt, f = b.evaluate_point({f"x{i}": float(v) for i, v in enumerate(x)})
    return np.array(list(f.values()))


# ---- closed forms ---------------------------------------------------------------------------------------------------
def zdt(i, x):
    n = len(x)
    g = 1 + 9 * x[1:].sum() / (n - 1)
    f1 = x[0]
    h = {1: 1 - np.sqrt(f1 / g), 2: 1 - (f1 / g) ** 2}[i]
    return np.array([f1, g * h])


def dtlz2_2obj(x, n_obj=2):
    g = ((x[n_obj - 1:] - 0.5) ** 2).sum()
    return np.array([(1 + g) * np.cos(x[0] * np.pi / 2), (1 + g) * np.sin(x[0] * np.pi / 2)])


def vlmop3(x):                                 # Viennet function
    r2 = x[0] ** 2 + x[1] ** 2
    return np.array([0.5 * r2 + np.sin(r2), (3 * x[0] - 2 * x[1] + 4) ** 2 / 8 + (x[0] - x[1] + 1) ** 2 / 27 + 15,
                     1 / (r2 + 1) - 1.1 * np.exp(-r2)])


def test_branin_currin_matches_botorch_float64():
    """Upstream evaluates BraninCurrin in float32 (the others in float64); check that costs <= 2e-3 after 3-dp rounding."""
    b = bench("BraninCurrin")
    for _ in range(10):
        x = np.round(rng.uniform(0.01, 1, 2), 3)
        np.testing.assert_allclose(evaluate(b, x), b.problem.evaluate_true(torch.tensor(x, dtype=torch.float64).view(1, -1)).numpy()[0], atol=2e-3)
    assert b.n_dim == 2 and b.n_obj == 2


@pytest.mark.parametrize("i", [1, 2])
def test_zdt_matches_closed_form(i):
    b = bench("ZDT", problem_id=f"zdt{i}")
    for _ in range(10):
        x = np.round(rng.uniform(0, 1, b.problem.n_var), 3)
        np.testing.assert_allclose(evaluate(b, x), zdt(i, x), atol=1.5e-3)


def test_dtlz2_matches_closed_form():
    b = bench("DTLZ", problem_id="dtlz2")
    assert b.problem.n_var == 6 and b.n_obj == 2
    for _ in range(10):
        x = np.round(rng.uniform(0, 1, 6), 3)
        np.testing.assert_allclose(evaluate(b, x), dtlz2_2obj(x), atol=1.5e-3)


def test_dtlz2_pareto_front_is_unit_circle():
    b = bench("DTLZ", problem_id="dtlz2")
    for t in np.linspace(0, 1, 7):
        f = evaluate(b, np.array([t, .5, .5, .5, .5, .5]))
        assert np.hypot(*f) == pytest.approx(1.0, abs=2e-3)


def test_vlmop_benchmark_is_vlmop3_not_vlmop2():
    """FINDING: upstream's 'VLMOP' is the 3-objective Viennet function (VLMOP3, 2 vars), whereas the plan listed VLMOP2.
    Phase 2 must use VLMOP3 (or write a VLMOP2 benchmark ourselves)."""
    b = bench("VLMOP")
    assert b.benchmark_name == "VLMOP3" and b.n_obj == 3
    for _ in range(10):
        x = np.round(rng.uniform(-3, 3, 2), 3)
        np.testing.assert_allclose(evaluate(b, x), vlmop3(x), atol=1.5e-3)


# ---- BoTorch-backed real-world problems ------------------------------------------------------------------------------
@pytest.mark.parametrize("name,cls_name", [("penicillin", "Penicillin"), ("vehicle_safety", "VehicleSafety"), ("car_side_impact", "CarSideImpact")])
def test_botorch_backed_benchmarks_match_reference_in_float64(name, cls_name):
    import botorch.test_functions.multi_objective as m
    ref = getattr(m, cls_name)()
    b = bench(name)
    lo, hi = ref.bounds[0].numpy(), ref.bounds[1].numpy()
    xs = [lo, hi, (lo + hi) / 2] + [lo + rng.uniform(0, 1, len(lo)) * (hi - lo) for _ in range(6)]
    for x in xs:
        x = np.round(x, 3)
        x = np.clip(x, lo, hi)
        want = ref.evaluate_true(torch.tensor(x, dtype=torch.float64).view(1, -1)).numpy()[0]
        np.testing.assert_allclose(evaluate(b, x), want, atol=1.5e-3, rtol=1e-6)


def test_penicillin_hardcoded_bounds_match_botorch_and_config():
    import json

    from botorch.test_functions.multi_objective import Penicillin
    b = bench("penicillin")
    ref = Penicillin()
    for i, (k, (lo, hi)) in enumerate(b.bounds.items()):
        assert (lo, hi) == pytest.approx((float(ref.bounds[0, i]), float(ref.bounds[1, i])))
    cfg = json.load(open("configurations/Penicillin/MOHOLLM-Penicillin-Context-Gemini.json"))
    assert {k: tuple(v) for k, v in cfg["parameter_constraints"].items()} == b.bounds


@pytest.mark.parametrize("name,n_dim,n_obj", [("penicillin", 7, 3), ("vehicle_safety", 5, 3), ("car_side_impact", 7, 4), ("BraninCurrin", 2, 2)])
def test_shapes_and_initialization_within_bounds(name, n_dim, n_obj):
    b = bench(name)
    pts = b.generate_initialization(5)
    assert len(pts) == 5 and all(len(p) == n_dim for p in pts)
    _, f = b.evaluate_point(pts[0])
    assert len(f) == n_obj and all(np.isfinite(v) for v in f.values())
    assert b.is_valid_candidate(pts[0])


def test_unknown_benchmark_is_an_error():
    with pytest.raises(ValueError):
        get_benchmark_fn({"benchmark": "nope"})
