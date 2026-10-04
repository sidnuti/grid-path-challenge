"""Paired statistics for policy comparisons. All comparisons in `experiments/` are paired: the same
world (seed + scenario) under common random numbers, one number per world per arm."""

from __future__ import annotations

import math
import random
import statistics as st


def paired_lift_pct(treat: float, ref: float) -> float:
    return (treat / ref - 1.0) * 100.0 if ref else 0.0


def bootstrap_ci(x: list[float], n: int = 10000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap CI of the mean. With < 3 points it returns (min, max) honestly."""
    if len(x) < 3:
        return (min(x), max(x)) if x else (float("nan"), float("nan"))
    rng = random.Random(seed)
    means = sorted(st.mean(rng.choices(x, k=len(x))) for _ in range(n))
    return means[int(n * alpha / 2)], means[int(n * (1 - alpha / 2)) - 1]


def t_ci(x: list[float], alpha: float = 0.05) -> tuple[float, float]:
    """Student-t CI of the mean (n-1 d.o.f.). The default for small numbers of worlds: the percentile
    bootstrap is too narrow at n ~ 6."""
    if len(x) < 2:
        return (float("nan"), float("nan"))
    from scipy import stats as sps
    h = sps.t.ppf(1 - alpha / 2, len(x) - 1) * st.stdev(x) / math.sqrt(len(x))
    return st.mean(x) - h, st.mean(x) + h


def sign_flip_p(x: list[float]) -> float:
    """Exact two-sided sign-flip permutation p-value for mean(x) = 0. Smallest possible p is 2/2^n
    (0.031 at n = 6)."""
    n = len(x)
    if n == 0:
        return float("nan")
    obs = abs(sum(x))
    cnt = 0
    for mask in range(1 << n):
        s = sum(v if mask >> i & 1 else -v for i, v in enumerate(x))
        cnt += abs(s) >= obs - 1e-12
    return cnt / (1 << n)


def summarize(x: list[float]) -> dict:
    """Mean, spread, t-based 95% CI (`ci95_lo/hi`), the bootstrap CI for comparison (`boot_lo/hi`), the
    exact sign-flip p, and this sample's own minimum detectable effect at its n."""
    if not x:
        return {"n": 0}
    lo, hi = t_ci(x)
    blo, bhi = bootstrap_ci(x)
    sd = st.stdev(x) if len(x) > 1 else 0.0
    return {"n": len(x), "mean": st.mean(x), "sd": sd,
            "min": min(x), "max": max(x), "ci95_lo": lo, "ci95_hi": hi, "boot_lo": blo, "boot_hi": bhi,
            "p_signflip": sign_flip_p(x) if len(x) <= 16 else float("nan"),
            "mde": minimum_detectable_effect(sd, len(x)),
            "all_positive": all(v > 0 for v in x), "all_negative": all(v < 0 for v in x)}


def minimum_detectable_effect(sd: float, n: int, z_alpha: float = 1.96, z_beta: float = 0.84) -> float:
    """Smallest true mean paired lift detectable with ~80% power at the 5% level, for a paired
    design with per-world SD `sd` and `n` worlds (normal approximation)."""
    return (z_alpha + z_beta) * sd / math.sqrt(n) if n > 0 else float("nan")


def worlds_needed(sd: float, effect: float, z_alpha: float = 1.96, z_beta: float = 0.84) -> int:
    return math.ceil(((z_alpha + z_beta) * sd / effect) ** 2) if effect > 0 else 10**9
