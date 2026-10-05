"""Module B (sim v2): who is searching. Brand-loyal vs open shoppers, stealing, reformulation.

Design: `design/02_simulator_v2_design.md` §3.

Each query q in city c has an intent mix π_{q,c} over segments (aurel, velora, nimbus, open), built from
the scenario's city-average table, a per-brand city tilt (§3.5) and seeded log-normal noise.

Ad orders are still drawn by the legacy auction (README M1). This module decides what an Aurel ad order
*took*, as a mixture over the segments that could have produced it. The weight of segment s is
π_s · r_s, where r_s is the rate at which one searcher of that segment becomes an attributed order:
  - open:          the nested-logit shelf (Module A): r = P_i · w_ad/w, split by `shelf.decompose`;
  - aurel-loyal:   buys some Aurel item with probability `loyal_buy`, choosing among visible Aurel items
                   in proportion to w^β e^{v}; an ad only moves them between Aurel SKUs (self / sibling).
                   If no Aurel item would be visible without the ad, they reformulate to the brand query
                   with probability ρ (counted as self: they still buy Aurel) and otherwise act as open;
  - b-loyal:       stolen through the ad (Simonov et al.): r = σ_b · steal_conv · w_ad, all "competitor",
                   with σ_b = d·σ_def + (1−d)·σ_undef, where d is the chance brand b defends with its own ad.

Two flows change *volumes*:
  - reformulation (§3.4): Aurel-loyal searchers on a generic query who do not see Aurel in the top
    positions move to the brand query K01 with probability ρ. The brand query gains
    Σ_q ρ·π^aurel_{q,c}·searches_q·(1 − min(1, vis_q)) searches, where vis_q is Aurel's visibility on q.
  - conquest loss (§3.2): on Aurel-owned queries with competitor presence κ (Module D), Aurel-loyal
    searchers are stolen at σ = s1·σ_def + (1−s1)·σ_undef, where s1 is Aurel's slot-1 share; the lost
    purchases come out of Aurel organic sales.
"""
from __future__ import annotations

import numpy as np

from .shelf import QueryShelf, decompose

SEGMENTS = ("aurel", "velora", "nimbus", "open")
COMP_ITEMS = {"velora": ("V1", "V2"), "nimbus": ("N1", "N2")}


def build_intent(spec: dict, keyword_ids, city_ids, seed: int) -> dict:
    """π per (query, city), with city tilt and seeded noise. Uses its own RNG stream (no legacy draws)."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, 2003]))
    tilt = spec.get("city_tilt", {})                     # {"aurel": {"BLR": 1.15, ...}, ...}
    sd = float(spec.get("city_noise_sigma", 0.08))
    mix = {}
    for k in keyword_ids:
        base = spec["mix"].get(k, {"open": 1.0})
        for c in city_ids:
            p = {}
            for b in SEGMENTS[:3]:
                v = base.get(b, 0.0)
                p[b] = v * tilt.get(b, {}).get(c, 1.0) * float(np.exp(rng.normal(0, sd))) if v > 0 else 0.0
            tot = sum(p.values())
            if tot > 0.95:
                p = {b: v * 0.95 / tot for b, v in p.items()}
            p["open"] = 1.0 - sum(p.values())
            mix[(k, c)] = p
    return mix


class Intent:
    def __init__(self, spec: dict, mix: dict):
        self.spec = spec
        self.mix = mix
        self.loyal_buy = float(spec.get("loyal_buy", 0.15))
        self.rho = float(spec.get("rho_reform", 0.4))
        self.s_def = float(spec.get("sigma_def", 0.03))
        self.s_undef = float(spec.get("sigma_undef", 0.30))
        self.steal_conv = float(spec.get("steal_conv", 0.3))
        self.defend = spec.get("defend", {})             # {"velora": {"K09": 0.9, "default": 0.3}}
        self.brand_query = spec.get("brand_query", "K01")
        self.reform_from = set(spec.get("reformulation_from", []))
        self.reform_conv = float(spec.get("reform_conv_mult", 1.0))   # reformulators are high-intent searchers

    def _sigma(self, b: str, kid: str) -> float:
        d = self.defend.get(b, {})
        d = float(d.get(kid, d.get("default", 0.3)))
        return d * self.s_def + (1 - d) * self.s_undef

    @staticmethod
    def _aurel_shares(shelf: QueryShelf, wa: np.ndarray) -> np.ndarray:
        w = shelf.w_org + wa
        s = np.where(shelf.own & (w > 0), np.power(np.where(w > 0, w, 1.0), shelf.beta) * np.exp(shelf.v), 0.0)
        tot = s.sum()
        return s / tot if tot > 0 else s

    def decompose(self, shelf: QueryShelf, w_ad: dict[str, float], city: str) -> dict[str, dict]:
        """Mixture of the per-segment splits of one attributed ad order (same schema as `shelf.decompose`)."""
        pi = self.mix.get((shelf.keyword_id, city), {"open": 1.0})
        open_split = decompose(shelf, w_ad)
        wa = np.zeros(len(shelf.items))
        for item, x in w_ad.items():
            wa[shelf.index(item)] = x
        p_open, _ = shelf.probs(wa)
        share = self._aurel_shares(shelf, wa)
        out = {}
        for item, x in w_ad.items():
            i = shelf.index(item)
            if x <= 0 or item not in open_split:
                continue
            wtot = shelf.w_org[i] + x
            parts = []                                    # (weight, split)
            # open shoppers
            parts.append((pi["open"] * p_open[i] * x / wtot, open_split[item]))
            # Aurel-loyal shoppers
            if pi.get("aurel", 0) > 0 and share[i] > 0:
                wl = wa.copy(); wl[i] = 0.0
                share_l = self._aurel_shares(shelf, wl)
                attr = self.loyal_buy * share[i] * x / wtot
                if share_l.sum() > 0:                     # some Aurel item visible without the ad
                    gain = self.loyal_buy * (share[i] - share_l[i])
                    inc = min(max(gain, 0.0), attr) / attr
                    loss = np.clip(share_l - share, 0.0, None); loss[i] = 0.0
                    sib = {shelf.items[j]: inc * loss[j] / loss.sum() for j in range(len(loss)) if loss[j] > 0} \
                        if loss.sum() > 0 else {}
                    sp = {"self": 1.0 - inc if sib else 1.0, "sibling": sib, "competitor": 0.0, "expansion": 0.0,
                          "excess": 0.0}
                else:                                     # invisible without the ad: reformulate or shop open
                    o = open_split[item]
                    sp = {"self": self.rho + (1 - self.rho) * o["self"],
                          "sibling": {k: (1 - self.rho) * v for k, v in o["sibling"].items()},
                          "competitor": (1 - self.rho) * o["competitor"],
                          "expansion": (1 - self.rho) * o["expansion"], "excess": 0.0}
                parts.append((pi["aurel"] * attr, sp))
            # competitor-loyal shoppers, stolen
            for b in ("velora", "nimbus"):
                if pi.get(b, 0) > 0:
                    parts.append((pi[b] * self._sigma(b, shelf.keyword_id) * self.steal_conv * min(x, 1.0),
                                  {"self": 0.0, "sibling": {}, "competitor": 1.0, "expansion": 0.0, "excess": 0.0}))
            tot = sum(w for w, _ in parts)
            if tot <= 0:
                out[item] = open_split[item]
                continue
            mix = {"self": 0.0, "sibling": {}, "competitor": 0.0, "expansion": 0.0, "excess": 0.0}
            for w, sp in parts:
                f = w / tot
                for k in ("self", "competitor", "expansion", "excess"):
                    mix[k] += f * sp[k]
                for s, v in sp["sibling"].items():
                    mix["sibling"][s] = mix["sibling"].get(s, 0.0) + f * v
            out[item] = mix
        return out

    def aurel_visibility(self, shelf: QueryShelf, w_ad: dict[str, float]) -> float:
        v = float(shelf.w_org[shelf.own].sum()) + sum(w_ad.values())
        return min(1.0, v)

    def reformulation_searches(self, kid: str, city: str, searches: float, vis: float) -> float:
        """Searches moved from generic query `kid` to the brand query in one daypart."""
        if kid not in self.reform_from:
            return 0.0
        return self.rho * self.mix.get((kid, city), {}).get("aurel", 0.0) * searches * (1 - vis)

    def conquest_loss(self, kid: str, city: str, searches: float, kappa: float, s1: float) -> float:
        """Aurel purchases lost to competitor ads on an Aurel-owned query, in one daypart (expected units)."""
        if kappa <= 0:
            return 0.0
        sigma = s1 * self.s_def + (1 - s1) * self.s_undef
        return searches * self.mix.get((kid, city), {}).get("aurel", 0.0) * self.loyal_buy * kappa * sigma
