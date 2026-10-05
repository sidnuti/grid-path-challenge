"""Initial design shared by every arm (design/04 §6: "initial design 5 Sobol points shared by all arms").

Scrambled Sobol in [0, 1]^d seeded by the world seed. The first `n` points of one sequence, so A1 (Sobol
search) extends the same sequence the other arms start from.
"""
from __future__ import annotations

import warnings

import numpy as np
from scipy.stats import qmc

N_INIT = 5


def sobol(d: int, n: int, seed: int) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")              # balance warning for n not a power of 2
        return np.round(qmc.Sobol(d, scramble=True, seed=seed).random(n), 4)   # 4 dp: what an LLM sees and echoes


def initial_design(d: int, seed: int, n: int = N_INIT) -> np.ndarray:
    return sobol(d, n, seed)
