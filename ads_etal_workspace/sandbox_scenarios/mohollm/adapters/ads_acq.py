"""Runtime-registered acquisition for arm A5 (random-in-leaf), without editing upstream.

Upstream's `RandomACQ` ignores `top_k` and returns a single int, which the partitioned loop cannot index
(`space_partitioning_mohollm.py:142`: TypeError), so upstream's random ablations keep an LLM surrogate.
`RandomTopKACQ` picks `top_k` distinct candidates uniformly at random (numpy global RNG, seeded by the runner),
so A5 is: kd-tree + region scoring as in A4, candidates sampled uniformly in the selected leaves, no LLM.
"""
from __future__ import annotations

import numpy as np

from mohollm.acquisition_functions.acquisition_function import ACQUISITION_FUNCTION


class RandomTopKACQ(ACQUISITION_FUNCTION):
    def select_candidate_point(self, candidate_evaluations, *args, **kwargs):
        k = min(int(kwargs.get("top_k") or 1), len(candidate_evaluations))
        idx = np.random.choice(len(candidate_evaluations), size=k, replace=False)
        if k == 1:
            return int(idx[0]), candidate_evaluations[int(idx[0])], []
        return idx, [candidate_evaluations[i] for i in idx], []


def install() -> None:
    from mohollm import settings
    settings.ACQUISITION_FUNCTIONS.setdefault("RandomTopKACQ", RandomTopKACQ)
