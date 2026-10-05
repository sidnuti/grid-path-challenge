"""Module A (sim v2): the shelf. A nested-logit choice model on each search-results page.

Design: `design/02_simulator_v2_design.md` §2. Replaces only step 6 of `market.py` (the "ad orders that
would have happened anyway" term). Searches, the auction, slot shares, OSA, budgets and the number of
ad orders are unchanged, so direct-ROAS calibration carries over.

Per query q the shelf lists own SKUs and competitor items (V1, V2, N1, N2), grouped in nests
(bar / liquid) plus the outside option (no purchase). Item i has visibility w_i = w_org(rank) + w_ad
and base utility v_i = log(appeal_i) + log(relevance_{q,i}):

    P(i|n) = w_i^β e^{v_i/λ_n} / Σ_{j∈n} w_j^β e^{v_j/λ_n}
    I_n    = λ_n log Σ_{j∈n} w_j^β e^{v_j/λ_n}
    P(n)   = e^{I_n} / (e^{V0_q} + Σ_m e^{I_m})

This is the doc's nested logit with V_i = λ_n β log w_i + v_i. Deviation from §2.2, recorded in
REPORT.md: the doc writes β log w inside V_i/λ, which makes within-nest share scale as w^{β/λ}
(w^2.9 at λ = 0.35), so an ad could gain more orders than it is credited with. Writing it as above
keeps "choice ∝ visibility" (§2.5, β = 1) and the doc's diversion formulas, which are stated per unit
of V_i.

V0_q is set per query so that the outside option takes `outside_share` of shoppers on the organic
shelf (no ads): the "category conversion" knob of §2.5.

Decomposition (§2.4) of the ad orders of own item i in one auction, by leave-one-out on i's ad:
    attributed  A_i = P_i · w_ad,i / w_i                  (the platform credits the click path)
    gain        G_i = P_i − P_i^{−ad}                      (what the ad changed)
    self        = 1 − min(G_i, A_i)/A_i                    (would have bought i anyway)
    the rest is split over the items that lost share, P_j^{−ad} − P_j, as
    sibling (other own SKUs) / competitor / expansion (the outside option).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .world import SLOT_VIEW_REL, SLOTS

OUTSIDE = "__none__"
# Organic view weight by rank: log-linear fit to the industry rank curve at ranks 1/5/9/13
# (1.00 / 0.41 / 0.17 / 0.08): exp(−κ(r−1)), least-squares κ ≈ 0.211, within 0.02 at all four ranks.
_KAPPA = float(np.polyfit([r - 1 for r in SLOTS], [-np.log(SLOT_VIEW_REL[r]) for r in SLOTS], 1)[0])


def organic_weight(rank) -> float:
    if rank is None or (isinstance(rank, float) and np.isnan(rank)):
        return 0.0
    return float(np.exp(-_KAPPA * (float(rank) - 1)))


@dataclass
class QueryShelf:
    """The static part of one query's shelf: items, nests, organic weights, base utilities, V0."""
    keyword_id: str
    items: list[str]
    own: np.ndarray        # bool per item
    nest: np.ndarray       # int nest index per item
    lam: np.ndarray        # λ per nest
    v: np.ndarray          # base utility per item
    w_org: np.ndarray      # organic visibility per item
    beta: float
    v0: float

    def probs(self, w_ad: np.ndarray | None = None) -> tuple[np.ndarray, float]:
        """Choice probabilities per item and for the outside option, at visibility w_org + w_ad."""
        w = self.w_org if w_ad is None else self.w_org + w_ad
        return nested_logit(w, self.v, self.nest, self.lam, self.beta, self.v0)

    def index(self, item: str) -> int:
        return self.items.index(item)


def nested_logit(w, v, nest, lam, beta, v0) -> tuple[np.ndarray, float]:
    p = np.zeros(len(w))
    on = w > 0
    expI = np.zeros(len(lam))
    within = np.zeros(len(w))
    for n in range(len(lam)):
        m = on & (nest == n)
        if not m.any():
            continue
        s = w[m] ** beta * np.exp(v[m] / lam[n])
        S = s.sum()
        within[m] = s / S
        expI[n] = np.exp(lam[n] * np.log(S))
    denom = np.exp(v0) + expI.sum()
    pn = expI / denom
    p[on] = within[on] * pn[nest[on]]
    return p, float(np.exp(v0) / denom)


def diversion(shelf: QueryShelf, i: int, w_ad: np.ndarray | None = None) -> dict[str, float]:
    """Closed-form D_{j→i} (§2.3) for every other item j and the outside option, per unit change of V_i."""
    w = shelf.w_org if w_ad is None else shelf.w_org + w_ad
    p, p0 = nested_logit(w, shelf.v, shelf.nest, shelf.lam, shelf.beta, shelf.v0)
    n = shelf.nest[i]
    lam = shelf.lam[n]
    pn = p[shelf.nest == n].sum()
    pin = p[i] / pn
    q = (1 / lam) * (1 - pin) + pin * (1 - pn)
    out = {}
    for j, item in enumerate(shelf.items):
        if j == i or w[j] <= 0:
            continue
        if shelf.nest[j] == n:
            out[item] = (p[j] / pn) * (1 / lam - 1 + pn) / q
        else:
            out[item] = p[j] / q
    out[OUTSIDE] = p0 / q
    return out


def build_shelves(spec: dict, keyword_sku, products, appeal: dict) -> dict[str, QueryShelf]:
    """One QueryShelf per keyword from the scenario's `shelf` block and the public keyword_sku table."""
    nests = spec["nests"]                                   # {"bar": {"lambda": .35, "sub_categories": [...]}, ...}
    nest_names = list(nests)
    sub_to_nest = {sc: k for k, n in nests.items() for sc in n["sub_categories"]}
    lam = np.array([nests[k]["lambda"] for k in nest_names], dtype=float)
    beta = float(spec.get("beta", 1.0))
    comp = spec["competitors"]                              # {"V1": {"nest": "bar", "appeal": 1.05, "keywords": {"K03": [rel, rank]}}}
    sub = dict(zip(products.sku_id, products.sub_category))
    outside = spec["outside_share"]                         # {"default": .7, "K01": .5, ...}
    shelves = {}
    for kid in sorted(set(keyword_sku.keyword_id) | {k for c in comp.values() for k in c["keywords"]}):
        items, own, nest, v, w_org = [], [], [], [], []
        for r in keyword_sku[keyword_sku.keyword_id == kid].itertuples():
            items.append(r.sku_id); own.append(True)
            nest.append(nest_names.index(sub_to_nest[sub[r.sku_id]]))
            v.append(np.log(appeal[r.sku_id]) + np.log(r.relevance))
            w_org.append(organic_weight(r.organic_rank))
        for cid, c in comp.items():
            if kid in c["keywords"]:
                rel, rank = c["keywords"][kid]
                items.append(cid); own.append(False)
                nest.append(nest_names.index(c["nest"]))
                v.append(np.log(c["appeal"]) + np.log(rel))
                w_org.append(organic_weight(rank))
        sh = QueryShelf(kid, items, np.array(own), np.array(nest), lam, np.array(v, dtype=float),
                        np.array(w_org, dtype=float), beta, 0.0)
        # V0: outside option takes `p0` of shoppers on the organic shelf
        p0 = float(outside.get(kid, outside["default"]))
        expI_sum = _sum_exp_inclusive(sh)
        sh.v0 = float(np.log(p0 / (1 - p0) * expI_sum)) if expI_sum > 0 else 0.0
        shelves[kid] = sh
    return shelves


def _sum_exp_inclusive(sh: QueryShelf) -> float:
    tot = 0.0
    on = sh.w_org > 0
    for n in range(len(sh.lam)):
        m = on & (sh.nest == n)
        if m.any():
            tot += float(np.exp(sh.lam[n] * np.log((sh.w_org[m] ** sh.beta * np.exp(sh.v[m] / sh.lam[n])).sum())))
    return tot


def decompose(shelf: QueryShelf, w_ad: dict[str, float]) -> dict[str, dict]:
    """Per own item with an ad in this auction: expected split of one attributed ad order.

    Returns {item: {"self": f, "sibling": {sku: f}, "competitor": f, "expansion": f, "excess": g}},
    fractions summing to 1. `excess` (diagnostic) is the gain beyond the attributed orders, which this
    model does not credit to anyone."""
    wa = np.zeros(len(shelf.items))
    for item, x in w_ad.items():
        wa[shelf.index(item)] = x
    p, p0 = shelf.probs(wa)
    out = {}
    for item, x in w_ad.items():
        i = shelf.index(item)
        if x <= 0 or p[i] <= 0:
            continue
        wl = wa.copy()
        wl[i] = 0.0
        pl, p0l = shelf.probs(wl)
        attr = p[i] * x / (shelf.w_org[i] + x)
        gain = p[i] - pl[i]
        inc = min(max(gain, 0.0), attr) / attr
        loss = np.clip(pl - p, 0.0, None)
        loss[i] = 0.0
        loss0 = max(p0l - p0, 0.0)
        tot = loss.sum() + loss0
        sib, compf = {}, 0.0
        if tot > 0:
            for j, it in enumerate(shelf.items):
                if loss[j] <= 0:
                    continue
                f = inc * loss[j] / tot
                if shelf.own[j]:
                    sib[it] = f
                else:
                    compf += f
            expf = inc * loss0 / tot
        else:
            expf = inc
        out[item] = {"self": 1.0 - inc, "sibling": sib, "competitor": compf, "expansion": expf,
                     "excess": max(gain - attr, 0.0) / attr}
    return out
