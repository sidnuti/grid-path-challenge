"""Sim v2 measurement lever: `request_holdout` (design/02 §7.2).

A holdout pauses one cell (campaign × keyword, i.e. SKU × city × keyword) for one run. Like a real lift test,
its result is a noisy estimate of the cell's brand-incremental revenue per day, with a 95% confidence
interval. The truth it estimates is the cell's expected brand-incremental revenue over the 7 days before the
holdout: (competitor + expansion) orders × ASP, from the shelf model's `truth_decomp`, or the legacy
incrementality × ad revenue when the shelf is off. The holdout's real cost is the sales lost while paused.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

HOLDOUT_STREAM = 5001
SE_REL, SE_FLOOR_INR = 0.25, 300.0
Z95 = 1.959964


def true_cell_value(world, cid: str, kid: str, day: int, facts: pd.DataFrame, decomp: pd.DataFrame | None) -> float:
    lo = day - 7
    if decomp is not None and len(decomp):
        d = decomp[(decomp.campaign_id == cid) & (decomp.keyword_id == kid) & (decomp.day >= lo) & (decomp.day < day)]
        if len(d):
            asp = world.public["products"].set_index("sku_id").asp_inr
            return float(((d.competitor + d.expansion) * d.sku_id.map(asp)).sum() / 7)
    f = facts[(facts.campaign_id == cid) & (facts.keyword_id == kid) & (facts.day >= lo) & (facts.day < day)]
    return float(f.ad_revenue_inr.sum() * world.truth["keywords"][kid]["incrementality"] / 7)


def readout(world, run: int, cid: str, kid: str, truth: float) -> dict:
    rng = np.random.default_rng(np.random.SeedSequence([world.seed, HOLDOUT_STREAM, run, zlib.crc32(f"{cid}|{kid}".encode())]))
    se = SE_REL * abs(truth) + SE_FLOOR_INR
    est = truth + rng.normal(0, se)
    return {"run": run, "campaign_id": cid, "keyword_id": kid, "est_inc_rev_per_day": round(est, 2),
            "se": round(se, 2), "ci_lo": round(est - Z95 * se, 2), "ci_hi": round(est + Z95 * se, 2)}
