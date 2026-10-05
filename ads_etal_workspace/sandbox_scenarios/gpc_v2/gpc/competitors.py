"""Module D (sim v2): competitor agents that pace a budget, plus opportunistic conquest of Aurel's brand query.

Design: `design/02_simulator_v2_design.md` §5.

Pacing. Each agent c (Velora, Nimbus) holds a bid level b_c (1.0 at the start). Its spend, in units of its
base budget, is s_c(t)·b_c^ε, where s_c(t) is the search index of its keywords (from the calendar), so
spend rises with both demand and bids. It updates once a day:

    b_c(t+1) = b_c(t) · exp(η · (B_c(t) − spend_c(t)) / B_c(t)),   B_c(t) = competitor_budget_mult(t)

The equilibrium is b* = (B/s)^{1/ε}: a festive budget ×2.5 against searches ×1.15 gives b* ≈ 1.40 at
ε = 2.3, the 30–50% CPM rise the doc targets (§5, gate §10 step 4). The clearing-price multiplier of a
keyword is Σ_c share_{c,k}·b_c + (1 − Σ_c share_{c,k})·b_rest (the long tail paces like an agent).
The search index s_c covers core keywords only (an ephemeral keyword's ×6 surge would swamp it). The per-auction
log-normal spread of `_slot_shares` is unchanged, so the auction keeps its closed form.

Opportunism. Per city, if Aurel's slot-1 share on the brand query stays below `threshold` for `days`
consecutive days, a competitor starts conquesting it: K01's clearing price rises by `bid_up` and its
conquest presence (used by the intent module's stealing channel) becomes `presence`. It stops after
Aurel's share is back above the threshold for `days` consecutive days.

Agent state depends on the day only, except for opportunism, which reacts to Aurel's own bids. That is
intended: pausing the brand keyword invites conquest. The state lives on the Market instance.
"""
from __future__ import annotations

import math

from .calendar import Calendar


class Competitors:
    def __init__(self, spec: dict, calendar: Calendar, city_ids: list[str]):
        self.spec = spec
        self.cal = calendar
        self.agents = spec["agents"]                     # {"velora": {"keywords": {"K03": 0.4, ...}}, ...}
        self.eps = float(spec.get("spend_elasticity", 2.3))
        self.eta = float(spec.get("eta", 0.5))
        self.bid = {a: 1.0 for a in self.agents}
        self.bid["rest"] = 1.0                           # the long tail paces too (its share = 1 − Σ named shares)
        # search index over core keywords only: an ephemeral keyword's surge (K11 ×6, 0 outside its window)
        # would otherwise swamp the index and pull the festive bid response down
        self.core = [k for k in {k for ag in self.agents.values() for k in ag["keywords"]} if k not in calendar.live]
        self.rest_core = list(spec.get("rest_keywords", self.core))
        opp = spec.get("opportunism", {})
        self.opp = opp
        self.opp_kw = opp.get("keyword", "K01")
        self.on = {c: False for c in city_ids}
        self.streak = {c: 0 for c in city_ids}

    def price_mult(self, kid: str, city: str) -> float:
        tot, share = 0.0, 0.0
        for a, ag in self.agents.items():
            s = ag["keywords"].get(kid, 0.0)
            tot += s * self.bid[a]
            share += s
        m = tot + (1 - share) * self.bid["rest"]
        if self.opp and kid == self.opp_kw and self.on[city]:
            m *= 1 + self.opp["bid_up"]
        return m

    def conquest_keywords(self) -> list[str]:
        ks = list(self.spec.get("conquest_base", {}))
        if self.opp and self.opp_kw not in ks:
            ks.append(self.opp_kw)
        return ks

    def conquest(self, kid: str, city: str) -> float:
        """Competitor ad presence on an Aurel-owned query (0–1): a baseline per query plus opportunism."""
        base = self.spec.get("conquest_base", {}).get(kid, 0.0)
        if self.opp and kid == self.opp_kw and self.on[city]:
            return max(base, float(self.opp["presence"]))
        return base

    def end_of_day(self, day: int, aurel_slot1_share: dict[str, float]) -> None:
        budget = self.cal.competitor_budget_mult(day)
        index = {a: {k: w for k, w in ag["keywords"].items() if k in self.core} for a, ag in self.agents.items()}
        index["rest"] = {k: 1.0 for k in self.rest_core}
        for a, kw in index.items():
            s = sum(w * self.cal.search_mult(k, day) for k, w in kw.items()) / sum(kw.values()) if kw else 1.0
            spend = s * self.bid[a] ** self.eps
            self.bid[a] *= math.exp(self.eta * (budget - spend) / budget)
        if self.opp:
            for c in self.on:
                low = aurel_slot1_share.get(c, 0.0) < self.opp["threshold"]
                if low != self.on[c]:
                    self.streak[c] += 1
                    if self.streak[c] >= self.opp["days"]:
                        self.on[c], self.streak[c] = low, 0
                else:
                    self.streak[c] = 0
