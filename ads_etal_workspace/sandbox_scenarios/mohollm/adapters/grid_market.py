"""GridMarketBenchmark: the Track-A ad-market black box as a MoHOLLM benchmark (design/04 §6 "Integration").

Upstream is not edited: its benchmark registry is a hard-coded `match`, so `runs/r_ads.py` passes an instance
straight to `Builder(cfg, benchmark=...)`. MoHOLLM minimises every metric (its `metrics_targets` is ignored by
the acquisition functions, region scorer and prompts), so maximised goals are negated:

    E1 (G-0): F1 = −IncRev (₹ lakh)
    E2 (G-1): F1 = −IncRev (₹ lakh), F2 = −S5 North slot-1 share (%), F3 = −S6 sell-through (%)

Values are scaled to O(1–100) so the LLM reads them easily (₹1 lakh = ₹100,000). Every evaluation, with all
diagnostics and constraint slacks, is appended to `self.log` (and to `evaluations.jsonl` in the work dir).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]                  # sandbox_scenarios/
for p in (ROOT, ROOT / "gpc_v2"):                          # bench, and the sim-v2 copy of the gpc package
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from bench.blackbox import BlackBox                         # noqa: E402
from bench.decode import Encoding                           # noqa: E402
from bench.design import initial_design                     # noqa: E402
from mohollm.benchmarks.benchmark import BENCHMARK          # noqa: E402

GOALS = {
    "G0": {"metrics": ["F1"], "budget_scale": False},
    "G1": {"metrics": ["F1", "F2", "F3"], "budget_scale": True},
}

DESCRIPTION = (
    "You are allocating a quick-commerce search-advertising programme for the personal-care brand Aurel (soaps, "
    "body wash, shower gel, a kids' soap and, during a festive window, a gift pack) across five Indian cities for six "
    "weekly runs. Each configuration is a set of normalised levers in [0, 1]. "
    "bid_brand, bid_generic and bid_competition scale the bids on brand keywords ('aurel'), generic keywords "
    "('soap', 'body wash', ...) and competitor brand keywords from 0.5x to 1.5x of the starting bid (0.5 = unchanged). "
    "bid_bar and bid_liquid scale bids for bar soaps and for liquids from 0.7x to 1.3x. "
    "share_north is the share of the daily budget given to the North (Delhi); share_west_of_rest is the part of the "
    "remaining budget given to the West (Mumbai, Pune), the rest goes to the South (Bengaluru, Hyderabad). "
    "daypart below 0.33 switches night ads off, 0.33-0.67 runs all day, above 0.67 runs afternoon and evening only. "
    "festive scales the gift pack's and the 'bath gift set' keyword's bids and budget during the festive window "
    "(0 = off, 1 = 2x). defend_threshold: K01 'aurel' bids are raised 1.5x in a city when the observed competitor "
    "pressure there exceeds it (1 = never defend, 0 = always defend). "
)
METRIC_TEXT = {
    "G0": "F1 is minus the brand's incremental revenue over the six weeks in lakh rupees (lower is better), measured "
          "against a world with no ads, at a fixed daily budget.",
    "G1": "F1 is minus the brand's incremental revenue in lakh rupees; F2 is minus the kids' soap S5 share of top-slot "
          "auctions in the North on 'kids soap', 'aurel' and 'soap' in percent; F3 is minus the gift pack's sell-through "
          "in percent of stock. budget_scale sets the daily budget from 0.8x to 1.2x of the warm-up spend. "
          "Lower is better for all three.",
}


def task_description(goal: str) -> str:
    return DESCRIPTION + METRIC_TEXT[goal]


class GridMarketBenchmark(BENCHMARK):
    def __init__(self, scenario: str, seed: int, goal: str = "G0", method_name: str = "ads",
                 model_name: str = "none", log_path: str | None = None):
        super().__init__()
        self.goal = goal
        self.enc = Encoding(budget_scale=GOALS[goal]["budget_scale"])
        self.bb = BlackBox(scenario, seed, self.enc)
        self.metrics = GOALS[goal]["metrics"]
        self.benchmark_name = f"GridMarket-{scenario}"
        self.method_name, self.model_name = method_name, model_name
        self.seed, self.problem_id = seed, f"{scenario}-{goal}"
        self.dims = self.enc.dims
        self.log: list[dict] = []
        self.log_path = Path(log_path) if log_path else None

    # ── config helpers ─────────────────────────────────────────────────────────
    def parameter_constraints(self) -> dict:
        return {k: [0.0, 1.0] for k in self.dims}

    # ── BENCHMARK interface ────────────────────────────────────────────────────
    def generate_initialization(self, n_points: int, **kwargs):
        X = initial_design(self.enc.d, self.seed, n_points)
        return [{k: round(float(v), 4) for k, v in zip(self.dims, row)} for row in X]

    def _x(self, point: dict) -> list[float]:
        return [float(point[k]) for k in self.dims]

    def evaluate_point(self, point, **kwargs):
        r = self.bb(self._x(point))
        f = {"F1": round(-r["inc_rev"] / 1e5, 4)}
        if self.goal == "G1":
            f["F2"] = round(-100 * r["f2_s5_north_slot1"], 4)
            st = r["f3_s6_sell_through"]
            f["F3"] = round(-100 * st, 4) if st == st else 0.0           # scenarios without S6: constant 0
        rec = {"point": point, "fvals": f, **{k: r[k] for k in r if k not in ("x",)}}
        self.log.append(rec)
        if self.log_path:
            with self.log_path.open("a") as fh:
                fh.write(json.dumps(rec, default=float) + "\n")
        return point, f

    def get_few_shot_samples(self, **kwargs):
        return []

    def get_metrics_ranges(self, **kwargs):
        return None

    def is_valid_candidate(self, candidate) -> bool:
        """Cheap: right keys, numeric, inside the box. Never simulates (Penicillin's version evaluates twice)."""
        try:
            return set(candidate) == set(self.dims) and all(0.0 <= float(candidate[k]) <= 1.0 for k in self.dims)
        except (TypeError, ValueError):
            return False

    def is_valid_evaluation(self, evaluation) -> bool:
        return all(isinstance(v, (int, float)) and math.isfinite(v) for v in evaluation.values())
