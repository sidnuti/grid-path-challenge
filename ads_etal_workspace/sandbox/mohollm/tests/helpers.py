"""Shared builders for MoHOLLM unit tests."""
import numpy as np

from mohollm.space_partitioning.kd_tree_partitioning import KDTreePartitioning
from mohollm.space_partitioning.utils import BoundingBox
from mohollm.statistics.statistics import Statistics


def hv2d(points, ref):
    """Exact 2-D hypervolume (minimisation) by sweep line. Independent of pymoo."""
    pts = sorted((tuple(p) for p in points if p[0] < ref[0] and p[1] < ref[1]))
    hv, best_f2 = 0.0, ref[1]
    for f1, f2 in pts:
        if f2 < best_f2:
            hv += (ref[0] - f1) * (best_f2 - f2)
            best_f2 = f2
    return hv


def make_partitioner(n_points, boundaries, range_keys, *, m0=5, lam=0, scaling=False, seed=0, categorical=None):
    """Returns (partitioner, points, fvals, statistics). `boundaries`: {dim: [lo, hi]} for range dims; categorical dims
    are given in `categorical` as {dim: [choices]} and also go into the bounding box as lists."""
    rng = np.random.default_rng(seed)
    categorical = categorical or {}
    points = []
    for _ in range(n_points):
        p = {d: round(float(rng.uniform(*b)), 4) for d, b in boundaries.items()}
        for d, ch in categorical.items():
            p[d] = ch[int(rng.integers(len(ch)))]
        points.append(p)
    fvals = [{"F1": float(rng.uniform()), "F2": float(rng.uniform())} for _ in points]
    bb = BoundingBox(volume=0.0, boundaries={**boundaries, **categorical}, range_parameter_keys=list(range_keys))
    bb.calculate_volume()
    st = Statistics()
    st.observed_configs, st.observed_fvals = list(points), list(fvals)
    kd = KDTreePartitioning()
    kd.bounding_box = bb
    kd.statistics = st
    kd.range_parameter_keys = list(range_keys)
    kd.integer_parameter_keys, kd.float_parameter_keys = [], list(range_keys)
    kd.space_partitioning_settings = {"adaptive_leaf_settings": {"m0": m0, "lam": lam, "use_dimension_scaling": scaling}}
    return kd, points, fvals, st
