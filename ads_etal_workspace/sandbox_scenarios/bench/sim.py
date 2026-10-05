"""Run a decoded policy through the v2 market without guardrails (design/03 G-0/G-1: only the encoding's box).

The 28-day warm-up is identical for every x on a world, so it is simulated once per (scenario, seed) and the
market state is snapshotted. Each evaluation restores the snapshot and simulates the 6 runs, re-decoding x on
each run's observation. Constraint classes C1–C9 are measured after the fact (bench.goals), never enforced here.
"""
from __future__ import annotations

import copy

import pandas as pd

from gpc.market import Market
from gpc.observation import Observation
from gpc.runner import ROAS_TOLERANCE, SimResult, public_extra
from gpc.world import N_RUNS, RUN_DAYS, WARMUP_DAYS, World

FRAMES = ("daily_facts", "campaign_daily", "sku_city_daily")
_NO_ACTIONS = pd.DataFrame(columns=["campaign_id", "keyword_id", "action_type", "new_value", "reason"])


class WarmStart:
    """Warm-up simulated once; `fork()` hands out an independent copy of the post-warm-up state."""

    def __init__(self, world: World):
        self.world = world
        self.market = Market(world)
        self.acc = {k: [] for k in FRAMES}
        self.hidden: dict[str, list] = {}
        camps, ck = world.public["campaigns"].copy(), world.public["campaign_keywords"].copy()
        for d in range(WARMUP_DAYS):
            for k, v in self.market.simulate_day(d, camps, ck).items():
                (self.acc[k] if k in self.acc else self.hidden.setdefault(k, [])).append(v)
        f = pd.concat(self.acc["daily_facts"])
        self.warm_droas = float(f.ad_revenue_inr.sum() / f.spend_inr.sum())

    def fork(self):
        market = copy.deepcopy(self.market, {id(self.world): self.world})
        return market, {k: list(v) for k, v in self.acc.items()}, {k: list(v) for k, v in self.hidden.items()}


def run(ws: WarmStart, policy, n_runs: int = N_RUNS, name: str = "decoded") -> SimResult:
    """`policy(obs) -> (campaigns, campaign_keywords)` is applied as-is (no guardrails) for each run."""
    world = ws.world
    market, acc, hidden = ws.fork()
    runs = []
    cur_c, cur_k = world.public["campaigns"], world.public["campaign_keywords"]
    for r in range(1, n_runs + 1):
        day = WARMUP_DAYS + (r - 1) * RUN_DAYS
        frames = {k: pd.concat(v, ignore_index=True) for k, v in acc.items()}
        obs = Observation(run=r, day=day, public=world.public, campaigns=cur_c.copy(), campaign_keywords=cur_k.copy(),
                          roas_floor=ws.warm_droas * (1 - ROAS_TOLERANCE), warmup_droas=ws.warm_droas,
                          extra=public_extra(world, hidden, day, frames["sku_city_daily"]), **frames)
        camps, ck = policy(obs)
        cur_c, cur_k = camps, ck
        runs.append({"run": r, "day": day, "campaigns": camps, "campaign_keywords": ck,
                     "proposed": _NO_ACTIONS, "final": _NO_ACTIONS})      # state is set directly, not via actions
        for d in range(day, day + RUN_DAYS):
            for k, v in market.simulate_day(d, camps, ck).items():
                (acc[k] if k in acc else hidden.setdefault(k, [])).append(v)
    frames = {k: pd.concat(v, ignore_index=True) for k, v in acc.items()}
    return SimResult(name, frames["daily_facts"], frames["campaign_daily"], frames["sku_city_daily"], runs,
                     ws.warm_droas, {k: pd.concat(v, ignore_index=True) for k, v in hidden.items()})
