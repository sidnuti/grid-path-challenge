"""Scripted L2′ planners for bounds ($0, no model). Offline tooling: `OraclePlanner` reads the world's
hidden truth through `oracle.cell_truth`, which the real harness never may.

    random  seeded random intents over every verb and a random cell / campaign scope (a floor for "any
            expressive plan at all")
    oracle  intents chosen from true incremental revenue per rupee at the current bid (an upper bound
            on what better *choices* through the same compiler could add, not a realistic model)
"""

from __future__ import annotations

import random

from gpc.world import World

from harness_l2p.intents import IntentPlan

from .oracle import cell_truth


class RandomPlanner:
    label = "random"

    def __init__(self, seed: int, n: int = 12):
        self.rng, self.n = random.Random(seed), n

    def __call__(self, brief) -> IntentPlan:
        c, r = brief.cells, brief.roles
        verbs = ["raise_bid", "cut_bid", "raise_budget", "cut_budget", "pause", "set_dayparts", "lead_market", "hold"]
        out = []
        for i in range(self.n):
            v = self.rng.choice(verbs)
            if v in ("raise_bid", "cut_bid", "pause"):
                x = c.iloc[self.rng.randrange(len(c))]
                scope = {"campaign_id": x.campaign_id, "keyword_id": x.keyword_id}
            elif v == "lead_market" and len(brief.markets):
                m = brief.markets.iloc[self.rng.randrange(len(brief.markets))]
                scope = {"sku_id": self.rng.choice(m.skus.split()).split(":")[0], "city_id": m.city_id, "keyword_id": m.keyword_id}
            else:
                scope = {"campaign_id": r.campaign_id.iloc[self.rng.randrange(len(r))]}
            dps = self.rng.sample(["night", "morning", "afternoon", "evening"], k=self.rng.randint(2, 4))
            out.append({"id": f"x{i}", "verb": v, "scope": scope, "size": self.rng.choice(["small", "medium", "large"]),
                        "dayparts": dps, "confidence": self.rng.random()})
        return IntentPlan.model_validate({"intents": out, "notes": "random"})


class OraclePlanner:
    label = "oracle"

    def __init__(self, world: World, raise_at: float = 2.0, cut_below: float = 0.8, budget_at: float = 1.5):
        ct = cell_truth(world).set_index(["campaign_id", "keyword_id"])
        self.vpi = ct.true_value_per_impr.to_dict()
        self.raise_at, self.cut_below, self.budget_at = raise_at, cut_below, budget_at

    def __call__(self, brief) -> IntentPlan:
        c = brief.cells.copy()
        c["true_iroas"] = [self.vpi.get((a, k), 0.0) * 1000.0 / b if b else 0.0 for a, k, b in zip(c.campaign_id, c.keyword_id, c.bid)]
        out = []
        up = c[(c.true_iroas >= self.raise_at) & (c.slot1_share < 0.8) & (c.verdict != "MISSES")].nlargest(10, "true_iroas")
        for x in up.itertuples():
            out.append({"id": f"u{len(out)}", "verb": "raise_bid", "scope": {"campaign_id": x.campaign_id, "keyword_id": x.keyword_id},
                        "size": "medium", "confidence": min(1.0, x.true_iroas / 10)})
        dn = c[c.true_iroas < self.cut_below].nsmallest(8, "true_iroas")
        for x in dn.itertuples():
            out.append({"id": f"d{len(out)}", "verb": "cut_bid", "scope": {"campaign_id": x.campaign_id, "keyword_id": x.keyword_id},
                        "size": "medium", "confidence": 0.5})
        w = c.assign(w=c.spend_7d.clip(lower=1)).groupby("campaign_id").apply(
            lambda g: (g.true_iroas * g.w).sum() / g.w.sum(), include_groups=False)
        capped = brief.roles.set_index("campaign_id").ran_out_7d >= 2
        for cid, v in w.items():
            if capped.get(cid, False) and v >= self.budget_at:
                out.append({"id": f"b{len(out)}", "verb": "raise_budget", "scope": {"campaign_id": cid}, "size": "medium",
                            "confidence": min(1.0, v / 5)})
        out.sort(key=lambda i: -i["confidence"])
        return IntentPlan.model_validate({"intents": out, "notes": "oracle"})
