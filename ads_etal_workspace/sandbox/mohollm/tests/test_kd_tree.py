"""space_partitioning/kd_tree_partitioning.py: leaves cover the box, are disjoint, every point is in exactly one leaf."""
import math

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from helpers import make_partitioner

pytestmark = pytest.mark.offline

BOX2 = {"x0": [0.0, 1.0], "x1": [0.0, 1.0]}
BOX3 = {"x0": [60.0, 120.0], "x1": [0.05, 18.0], "x2": [293.0, 303.0]}


def cells(regions, dims):
    return [np.array([r.boundaries[d] for d in dims], dtype=float) for r in regions]    # (D, 2) per region


@pytest.mark.parametrize("box,n,leaf", [(BOX2, 40, 5), (BOX2, 100, 8), (BOX3, 60, 5), (BOX3, 25, 3)])
def test_leaves_cover_the_box_and_are_disjoint(box, n, leaf):
    kd, pts, fv, _ = make_partitioner(n, box, box.keys(), m0=leaf)
    regions = kd.partition(pts, fv)
    dims = list(box)
    cs = cells(regions, dims)
    box_vol = np.prod([b[1] - b[0] for b in box.values()])
    assert sum(np.prod(c[:, 1] - c[:, 0]) for c in cs) == pytest.approx(box_vol, rel=1e-9)     # cover (no gaps, no overlap)
    for i in range(len(cs)):                                                                    # pairwise interior-disjoint
        for j in range(i + 1, len(cs)):
            overlap = np.minimum(cs[i][:, 1], cs[j][:, 1]) - np.maximum(cs[i][:, 0], cs[j][:, 0])
            assert not np.all(overlap > 1e-12), (i, j)
    assert sum(r.normalized_volume for r in regions) == pytest.approx(1.0, rel=1e-9)


@pytest.mark.parametrize("box,n", [(BOX2, 40), (BOX3, 60)])
def test_every_point_is_in_exactly_one_leaf(box, n):
    kd, pts, fv, _ = make_partitioner(n, box, box.keys())
    regions = kd.partition(pts, fv)
    idx = [i for r in regions for i in r.points_indices]
    assert sorted(idx) == list(range(n))                                                       # a partition of the index set
    for r in regions:
        for i, p in zip(r.points_indices, r.points):
            assert p == pts[i]
            assert all(r.boundaries[d][0] - 1e-9 <= p[d] <= r.boundaries[d][1] + 1e-9 for d in box)   # inside its closed cell


@settings(max_examples=40, deadline=None)
@given(n=st.integers(8, 80), seed=st.integers(0, 10_000), m0=st.integers(2, 12))
def test_partition_properties_hold_for_random_data(n, seed, m0):
    kd, pts, fv, _ = make_partitioner(n, BOX3, BOX3.keys(), m0=m0, seed=seed)
    regions = kd.partition(pts, fv)
    assert sorted(i for r in regions for i in r.points_indices) == list(range(n))
    assert sum(np.prod([r.boundaries[d][1] - r.boundaries[d][0] for d in BOX3]) for r in regions) == pytest.approx(
        np.prod([b[1] - b[0] for b in BOX3.values()]), rel=1e-9)
    assert len(regions) >= 1


def test_leaf_size_bounds_points_per_region():
    kd, pts, fv, _ = make_partitioner(100, BOX2, BOX2.keys(), m0=6)
    regions = kd.partition(pts, fv)
    assert max(len(r.points) for r in regions) <= kd.adaptive_leafsize(100, 2)
    assert len(regions) > 1


@pytest.mark.parametrize("t,d,m0,lam,scaling", [(0, 2, 5, 0.0, True), (10, 2, 5, 3.0, True), (50, 7, 5, 2.5, True),
                                                (50, 7, 5, 2.5, False), (100, 3, 4, 1.0, True)])
def test_adaptive_leafsize_formula(t, d, m0, lam, scaling):
    kd, *_ = make_partitioner(10, BOX2, BOX2.keys(), m0=m0, lam=lam, scaling=scaling)
    expected = int(m0 * d if scaling else m0) + int(math.ceil(lam * math.log1p(t)))
    assert kd.adaptive_leafsize(t, d) == expected


def test_leaf_size_grows_with_iteration():
    kd, *_ = make_partitioner(10, BOX2, BOX2.keys(), m0=5, lam=3.0, scaling=True)
    sizes = [kd.adaptive_leafsize(t, 2) for t in (0, 5, 20, 80)]
    assert sizes == sorted(sizes) and sizes[-1] > sizes[0]


def test_categorical_dimension_is_handled():
    cat = {"op": ["conv", "pool", "skip", "zero"]}
    kd, pts, fv, _ = make_partitioner(60, {"x0": [0.0, 1.0]}, ["x0"], m0=4, categorical=cat)
    regions = kd.partition(pts, fv)
    assert sorted(i for r in regions for i in r.points_indices) == list(range(60))
    covered = set()
    for r in regions:
        assert set(r.boundaries["op"]) <= set(cat["op"])
        for p in r.points:
            assert p["op"] in r.boundaries["op"]
        covered |= set(r.boundaries["op"])
    assert covered == set(cat["op"])                        # every choice belongs to some region


def test_categorical_cells_may_overlap_documented():
    """Upstream detail: for categorical dims a cell [min, max] on the *index* axis is mapped back with int(round(.)) on both
    ends, so neighbouring cells can share a choice (Python's banker's rounding of x.5). Not a bug for sampling, but 'disjoint'
    only holds for range dims. Pin the behaviour so a future change is noticed."""
    cat = {"op": ["a", "b", "c", "d", "e"]}
    kd, pts, fv, _ = make_partitioner(80, {"x0": [0.0, 1.0]}, ["x0"], m0=3, categorical=cat, seed=3)
    regions = kd.partition(pts, fv)
    total_choice_slots = sum(len(r.boundaries["op"]) for r in regions)
    assert total_choice_slots >= len(cat["op"])


def test_empty_input_returns_no_regions():
    kd, *_ = make_partitioner(5, BOX2, BOX2.keys())
    assert kd.partition([], []) == []


def test_missing_bounding_box_is_an_error():
    kd, pts, fv, _ = make_partitioner(5, BOX2, BOX2.keys())
    kd.bounding_box = None
    with pytest.raises(ValueError):
        kd.partition(pts, fv)
