"""Diagnose: the one place the harness touches `gpc.engine` (the public, deterministic layer —
never `gpc.market` or `gpc.world` truth). Everything downstream works off this dict."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from gpc.engine.grid import build_grid
from gpc.engine.loop import campaign_pacing, cell_verdicts
from gpc.engine.traversal import choose_bids
from gpc.observation import Observation


@dataclass
class Diagnostics:
    grid: pd.DataFrame
    verdicts: pd.DataFrame
    pacing: pd.DataFrame
    bids: pd.DataFrame
    options: pd.DataFrame


def diagnose(obs: Observation) -> Diagnostics:
    grid = build_grid(obs)
    verdicts = cell_verdicts(obs)
    pacing = campaign_pacing(obs)
    bids, options = choose_bids(obs, grid, verdicts)
    return Diagnostics(grid=grid, verdicts=verdicts, pacing=pacing, bids=bids, options=options)
