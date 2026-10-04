"""Scripted stand-ins for the LLM, for X5.1 (bounds on what each leaf could add) and X5.2 (trigger rates).
They implement the harness's `complete_json(system, user, schema, timeout, **kw) -> (dict, Usage)` contract
and cost $0. Offline tooling: the `oracle` mode reads `World.truth`, which the real harness never may.

Modes (per leaf; a leaf not listed in `leaves` raises, so `leaf()` absorbs it into the default = absent):
  always_yes  the *active* answer: extend raise (L1 x1.5) / confirm shock (L2) / flip to the non-mechanical
              leader (L3) / explore (L4) / veto (L6)
  always_no   the passive answer: dampen raise (L1 x0.5) / deny shock / keep mechanical leader / no explore / no veto
  random      a seeded coin / uniform draw per call
  oracle      best effort from hidden truth (an UPPER bound for a leaf, not a realistic model):
    L1, L4  true incremental value per slot-1 impression x 1000 / CPM bid > 1  (a proxy for true iROAS)
    L2      an injected demand shock is active on this keyword today
    L3      the candidate with the highest true incremental value per impression
    L6      veto iff the spend-weighted true iROAS proxy of the large raises is < 1

The current simulation day is set by `DayAwareHarness` (needed only for the L2 oracle).
"""

from __future__ import annotations

import random
import re

import pandas as pd

from gpc.world import World
from harness.llm.client import Usage
from harness.policy import HTNHarness

from .oracle import cell_truth

MODES = ("always_yes", "always_no", "random", "oracle")
LEAVES = ("L1_value", "L2_shock", "L3_sibling", "L4_explore", "L6_review")


class ScriptedLLM:
    def __init__(self, world: World, mode: str, leaves=LEAVES, seed: int = 0):
        assert mode in MODES
        self.mode, self.leaves = mode, set(leaves)
        self.rng = random.Random(seed)
        self.day = 0
        self.t = world.truth
        ct = cell_truth(world).set_index(["campaign_id", "keyword_id"])
        self.vpi = ct.true_value_per_impr.to_dict()                    # INR per slot-1 impression
        self.calls: dict[str, int] = {}
        self.answers: dict[str, list] = {}

    # ── helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _f(pat: str, text: str, cast=str):
        m = re.search(pat, text)
        return cast(m.group(1)) if m else None

    def _iroas(self, camp: str, kw: str, cpm: float) -> float:
        return self.vpi.get((camp, kw), 0.0) * 1000.0 / cpm if cpm else 0.0

    def _demand_shock_active(self, kw: str) -> bool:
        return any(s["kind"] == "demand" and kw in s.get("keyword_ids", ()) and s["from_day"] <= self.day <= s.get("to_day", 10**9)
                   for s in self.t["shocks"])

    # ── per-leaf answers ──────────────────────────────────────────────────────
    def _l1(self, u):
        camp, kw = self._f(r"campaign ([^,\s]+),", u), self._f(r"keyword (\S+) \(", u)
        proposed = self._f(r"proposed new bid: INR (\d+(?:\.\d+)?)", u, float)
        m = self.mode
        mult = {"always_yes": 1.5, "always_no": 0.5}.get(m)
        if m == "random":
            mult = self.rng.uniform(0.5, 1.5)
        if m == "oracle":
            mult = 1.5 if self._iroas(camp, kw, proposed or 0.0) > 1.0 else 0.5
        return {"bid_multiplier": mult, "confidence": 0.9}

    def _l2(self, u):
        kw = self._f(r"keyword ([^\s.]+)\.", u)
        m = self.mode
        yes = {"always_yes": True, "always_no": False}.get(m)
        if m == "random":
            yes = self.rng.random() < 0.5
        if m == "oracle":
            yes = self._demand_shock_active(kw)
        return {"is_shock": yes, "magnitude": 3.0 if yes else 0.0, "direction": "surge" if yes else "none", "confidence": 0.9}

    def _l3(self, u):
        rows = re.findall(r"^- (\S+), (\S+), ([\d.eE+-]+), ([\d.]+)$", u, flags=re.M)
        kw = self._f(r"keyword (\S+)\.", u) or self._f(r"keyword (\S+),", u)
        ids = [r[0] for r in rows]
        scores = [float(r[2]) for r in rows]
        top = ids[max(range(len(ids)), key=scores.__getitem__)]
        other = [i for i in ids if i != top]
        m = self.mode
        if m == "always_no":
            pick = top
        elif m == "always_yes":
            pick = other[0] if other else top
        elif m == "random":
            pick = self.rng.choice(ids)
        else:
            kw = kw.rstrip(".,")
            pick = max(ids, key=lambda c: self.vpi.get((c, kw), 0.0))
        return {"leader_campaign_id": pick, "confidence": 0.9}

    def _l4(self, u):
        camp = self._f(r"campaign ([^,\s]+),", u)
        kw = self._f(r"keyword (\S+) \(", u)
        live = self._f(r"Live bid: INR (\d+(?:\.\d+)?)", u, float) or 0.0
        m = self.mode
        yes = {"always_yes": True, "always_no": False}.get(m)
        if m == "random":
            yes = self.rng.random() < 0.5
        if m == "oracle":
            yes = self._iroas(camp, kw, live) > 1.0
        return {"explore": yes, "max_spend_inr_day": 1000.0 if yes else 0.0}

    def _l6(self, u):
        rows = re.findall(r"^- (\S+)/(\S+) \w+: INR (\d+(?:\.\d+)?)/day", u, flags=re.M)
        m = self.mode
        veto = {"always_yes": True, "always_no": False}.get(m)
        if m == "random":
            veto = self.rng.random() < 0.5
        if m == "oracle":
            tot = sum(float(r[2]) for r in rows) or 1.0
            # no live CPM in this prompt: use each cell's starting bid as the CPM reference
            bids = self._start_bid
            w = sum(float(r[2]) * self._iroas(r[0], r[1], bids.get((r[0], r[1]), 0.0)) for r in rows) / tot
            veto = w < 1.0
        return {"veto": veto, "reason": "scripted"}

    def attach_start_bids(self, world: World):
        ck = world.public["campaign_keywords"]
        self._start_bid = {(r.campaign_id, r.keyword_id): r.bid_cpm_inr for r in ck.itertuples()}

    # ── LLMClient contract ────────────────────────────────────────────────────
    def complete_json(self, system, user, schema, timeout, **kw):
        leaf = kw.get("leaf")
        if leaf not in self.leaves:
            raise RuntimeError(f"leaf not scripted for this arm: {leaf}")
        out = {"L1_value": self._l1, "L2_shock": self._l2, "L3_sibling": self._l3,
               "L4_explore": self._l4, "L6_review": self._l6}[leaf](user)
        self.calls[leaf] = self.calls.get(leaf, 0) + 1
        self.answers.setdefault(leaf, []).append(out)
        return out, Usage(calls=1)


class DayAwareHarness(HTNHarness):
    """HTNHarness that tells a ScriptedLLM the current day (only the L2 oracle uses it)."""

    def recommend(self, obs):
        if isinstance(self._llm_override, ScriptedLLM):
            self._llm_override.day = obs.day
        return super().recommend(obs)
