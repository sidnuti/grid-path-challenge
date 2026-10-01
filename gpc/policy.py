"""Policies. A policy maps an Observation to a list of actions. That is the whole contract.

    class MyPolicy(Policy):
        name = "mine"
        def recommend(self, obs: Observation) -> pd.DataFrame:
            ...   # columns: campaign_id, keyword_id, action_type, new_value, reason

Action types: increase_cpm / reduce_cpm / pause_keyword (need keyword_id), increase_budget /
reduce_budget, set_dayparts (new_value = comma list, e.g. "morning,afternoon,evening").
Every action then passes the guardrail layer (gpc/guardrails.py) before it reaches the market.
"""

from __future__ import annotations

import pandas as pd

from .engine.grid import build_grid
from .engine.ledger import build_actions
from .engine.loop import campaign_pacing, cell_verdicts
from .engine.traversal import traverse
from .observation import Observation


class Policy:
    name = "policy"
    last_trace: dict | None = None

    def recommend(self, obs: Observation) -> pd.DataFrame:  # pragma: no cover - interface
        raise NotImplementedError


class NoOpPolicy(Policy):
    """Leaves every campaign exactly as it started."""
    name = "no_op"

    def recommend(self, obs: Observation) -> pd.DataFrame:
        self.last_trace = None
        return pd.DataFrame(columns=["campaign_id", "keyword_id", "action_type", "new_value", "reason"])


class DeterministicTraversal(Policy):
    """The baseline: grid → loop verdicts → traversal (bid → money → hours) → ledger."""
    name = "deterministic_traversal"

    def recommend(self, obs: Observation) -> pd.DataFrame:
        grid = build_grid(obs)
        verdicts = cell_verdicts(obs)
        pacing = campaign_pacing(obs)
        tr = traverse(obs, grid, verdicts, pacing)
        actions, ledger_log = build_actions(obs, tr, pacing)
        self.last_trace = {"grid": grid, "verdicts": verdicts, "pacing": pacing, "bid_choices": tr.bids, "bid_options": tr.options,
                           "sources": tr.sources, "demands": tr.demands, "transfers": tr.transfers,
                           "dayparts": tr.dayparts, "ledger_log": ledger_log, "notes": tr.notes}
        return actions
