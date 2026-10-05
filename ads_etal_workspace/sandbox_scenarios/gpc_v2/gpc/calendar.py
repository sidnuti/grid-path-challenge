"""Module C (sim v2): calendar. Seasonal, festive and ephemeral demand, pull-forward.

Design: `design/02_simulator_v2_design.md` §4. Everything here is a deterministic function of the day
index and the scenario's `calendar` block, so it is identical under any policy (common random numbers).

    festive m_k(t) = 1 + (A_k − 1)·exp(−(t − t*)² / 2w²) for t in [t* − ramp, t* + tail], w = ramp/2
    pull-forward:  over the `days_after` days after the window, m_k = 1 − ρ·S_k/days_after,
                   S_k = Σ_window (m_k(t) − 1), so Σ dip = ρ·Σ excess exactly (gate, §10 step 3)
    seasonal:      m_k(t) = 1 + amp·cos(2π(t − peak)/period)
    ephemeral:     a keyword or SKU exists only on days [live_from, live_to]
"""
from __future__ import annotations

import math


class Calendar:
    def __init__(self, spec: dict):
        self.spec = spec or {}
        self.events = self.spec.get("events", [])
        self.seasonal = self.spec.get("seasonal", [])
        self.live = {e["id"]: (e["live_from"], e["live_to"])
                     for e in self.spec.get("ephemeral_keywords", []) + self.spec.get("ephemeral_skus", [])}
        self._excess = {}                                   # (event id, keyword) → S_k
        for ev in self.events:
            pf = ev.get("pull_forward")
            if not pf:
                continue
            lo, hi = self.window(ev)
            for k in pf["keywords"]:
                self._excess[(ev["id"], k)] = sum(self._festive(ev, k, t) - 1 for t in range(lo, hi + 1))

    # ── windows and phases ──────────────────────────────────────────────────────
    @staticmethod
    def window(ev: dict) -> tuple[int, int]:
        return ev["peak_day"] - ev["ramp_days"], ev["peak_day"] + ev.get("tail_days", 0)

    def in_window(self, day: int) -> bool:
        return any(lo <= day <= hi for lo, hi in map(self.window, self.events))

    def phase(self, day: int) -> str:
        for ev in self.events:
            lo, hi = self.window(ev)
            post = ev.get("pull_forward", {}).get("days_after", 0)
            if lo <= day < ev["peak_day"] - 2:
                return "ramp"
            if ev["peak_day"] - 2 <= day <= ev["peak_day"] + 1:
                return "peak"
            if ev["peak_day"] + 1 < day <= hi:
                return "tail"
            if hi < day <= hi + post:
                return "post"
        return "normal"

    def is_live(self, entity: str, day: int) -> bool:
        if entity not in self.live:
            return True
        lo, hi = self.live[entity]
        return lo <= day <= hi

    # ── multipliers ─────────────────────────────────────────────────────────────
    @staticmethod
    def _festive(ev: dict, k: str, t: int) -> float:
        a = ev.get("demand", {}).get(k)
        lo, hi = Calendar.window(ev)
        if a is None or not lo <= t <= hi:
            return 1.0
        w = ev["ramp_days"] / 2
        return 1 + (a - 1) * math.exp(-((t - ev["peak_day"]) ** 2) / (2 * w * w))

    def search_mult(self, k: str, t: int) -> float:
        if not self.is_live(k, t):
            return 0.0
        m = 1.0
        for ev in self.events:
            m *= self._festive(ev, k, t)
            pf = ev.get("pull_forward")
            if pf and k in pf["keywords"]:
                hi = self.window(ev)[1]
                if hi < t <= hi + pf["days_after"]:
                    m *= 1 - pf["rho"] * self._excess[(ev["id"], k)] / pf["days_after"]
        for s in self.seasonal:
            if k in s["keywords"]:
                m *= 1 + s["amp"] * math.cos(2 * math.pi * (t - s["peak_day"]) / s["period_days"])
        return m

    def evening_lift(self, t: int) -> float:
        for ev in self.events:
            lo, hi = self.window(ev)
            if lo <= t <= hi:
                return float(ev.get("evening_intent_lift", 1.0))
        return 1.0

    def competitor_budget_mult(self, t: int) -> float:
        """Smooth festive budget curve for competitor agents (same shape as the demand curve)."""
        m = 1.0
        for ev in self.events:
            a = ev.get("competitor_budget_mult")
            lo, hi = self.window(ev)
            if a and lo <= t <= hi:
                w = ev["ramp_days"] / 2
                m *= 1 + (a - 1) * math.exp(-((t - ev["peak_day"]) ** 2) / (2 * w * w))
        return m
