"""Params: the one knob set System 2 is allowed to tune. Loaded from
`harness/params/default.json`, overridable by the `PARAMS_PATH` env var (a path to another
JSON file with the same shape). Values are read fresh at `load_params()` time — nothing caches
across runs, so an S2 learner can write a new file and the next run picks it up.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PARAMS_PATH = Path(__file__).resolve().parent / "params" / "default.json"


@dataclass
class Params:
    version: str = "0"
    depth: str = "L0"                      # L0 tools-only | L1 + leaves | L2 + review/debate
    headroom_margin: float = 0.02
    headroom_front_load: bool = True
    headroom_min_allowance_inr_day: float = 300.0
    run_allowance_frac: tuple = (0.10, 0.15, 0.20, 0.20, 0.20, 0.15)
    sibling_leader_min_slot1_share: float = 0.80
    shock_z_reach: float = 2.5
    shock_z_cpm: float = 2.5
    shock_z_osa: float = 2.0
    shock_lookback_days: int = 21
    shock_recent_days: int = 7
    explore_enabled: bool = False
    explore_max_thin_cells: int = 0
    explore_spend_cap_inr_day: float = 0.0
    budget_runout_min_days: int = 2
    llm_max_usd_per_run: float = 2.0
    llm_review_threshold_inr: float = 500.0
    verify_max_repairs: int = 1
    raw: dict = field(default_factory=dict, repr=False, compare=False)

    def allowance_frac(self, run: int) -> float:
        """Run is 1-based; falls back to the schedule's last value past its length."""
        idx = min(run - 1, len(self.run_allowance_frac) - 1)
        return float(self.run_allowance_frac[idx])

    def to_dict(self) -> dict:
        """The nested JSON shape `load_params`/`_from_dict` reads — the inverse of `_from_dict`,
        so `Params.to_dict()` round-trips through a file via `PARAMS_PATH`. Used by
        `harness/s2/learner_stub.py` to write out a proposed params file."""
        return {
            "version": self.version, "depth": self.depth,
            "headroom": {"margin": self.headroom_margin, "front_load": self.headroom_front_load,
                        "run_allowance_frac": list(self.run_allowance_frac),
                        "min_allowance_inr_day": self.headroom_min_allowance_inr_day},
            "siblings": {"leader_min_slot1_share": self.sibling_leader_min_slot1_share},
            "shocks": {"z_reach": self.shock_z_reach, "z_cpm": self.shock_z_cpm, "z_osa": self.shock_z_osa,
                      "lookback_days": self.shock_lookback_days, "recent_days": self.shock_recent_days},
            "explore": {"enabled": self.explore_enabled, "max_thin_cells": self.explore_max_thin_cells,
                       "spend_cap_inr_day": self.explore_spend_cap_inr_day},
            "budget": {"runout_min_days": self.budget_runout_min_days},
            "llm": {"max_usd_per_run": self.llm_max_usd_per_run,
                   "review_threshold_inr": self.llm_review_threshold_inr},
            "verify": {"max_repairs": self.verify_max_repairs},
        }


def _from_dict(d: dict) -> Params:
    h, sib, sh, ex, b, llm, v = (d.get(k, {}) for k in
        ("headroom", "siblings", "shocks", "explore", "budget", "llm", "verify"))
    return Params(
        version=d.get("version", "0"),
        depth=d.get("depth", "L0"),
        headroom_margin=h.get("margin", 0.02),
        headroom_front_load=h.get("front_load", True),
        run_allowance_frac=tuple(h.get("run_allowance_frac", (0.10, 0.15, 0.20, 0.20, 0.20, 0.15))),
        headroom_min_allowance_inr_day=h.get("min_allowance_inr_day", 300.0),
        sibling_leader_min_slot1_share=sib.get("leader_min_slot1_share", 0.80),
        shock_z_reach=sh.get("z_reach", 2.5),
        shock_z_cpm=sh.get("z_cpm", 2.5),
        shock_z_osa=sh.get("z_osa", 2.0),
        shock_lookback_days=sh.get("lookback_days", 21),
        shock_recent_days=sh.get("recent_days", 7),
        explore_enabled=ex.get("enabled", False),
        explore_max_thin_cells=ex.get("max_thin_cells", 0),
        explore_spend_cap_inr_day=ex.get("spend_cap_inr_day", 0.0),
        budget_runout_min_days=b.get("runout_min_days", 2),
        llm_max_usd_per_run=llm.get("max_usd_per_run", 2.0),
        llm_review_threshold_inr=llm.get("review_threshold_inr", 500.0),
        verify_max_repairs=v.get("max_repairs", 1),
        raw=d,
    )


def load_params(path: str | Path | None = None) -> Params:
    p = Path(path or os.environ.get("PARAMS_PATH") or DEFAULT_PARAMS_PATH)
    return _from_dict(json.loads(p.read_text()))
