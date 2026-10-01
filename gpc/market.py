"""The hidden market simulator. Turns a campaign configuration into one day of observed data.

Policies never import this module. They see only what it emits (daily facts, campaign pacing,
SKU × city offtake), exactly as an operator would see platform reports.

Mechanics, per day and daypart (night → morning → afternoon → evening):

1. Searches = 30-day volume / 30 × city share × daypart share × city-keyword affinity
   × weekend lift × noise × any demand shock.
2. Auction: each slot (1 / 5 / 9 / 13) has a median clearing CPM = rank-1 CPM × city index
   × daypart level × slot price ratio × daily noise × any price shock. Competitor bids vary from
   auction to auction (log-normal, σ = 0.30), so a bid wins a SHARE of auctions at each slot and
   pays the clearing price of the auctions it wins. Bidding higher wins the top slot more often
   but pays more for those marginal auctions: returns diminish. Two Aurel campaigns on the same
   keyword in the same city compete: where the higher bid holds a slot, the lower one drops a slot.
3. Impressions = searches × slot view ratio × on-shelf availability (ads only serve where in stock).
4. Budget: spend accrues daypart by daypart; a campaign that hits its daily budget stops serving
   for the rest of the day.
5. Ad orders ~ Poisson(impressions × slot conversion × keyword intent × relevance × SKU appeal).
6. Organic orders ~ Poisson(base units × city share × weekly × availability × noise), minus the
   ad orders that would have happened anyway (1 − incrementality). Total offtake = organic + ad.

Every random draw is indexed by (day, entity), never by what the policy did, so two policies run
on the same seed face the same market (common random numbers).
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
from scipy.stats import norm, poisson

from .world import (DAYPART_PRICE, DAYPARTS, SLOT_CONV, SLOT_PRICE_REL, SLOT_VIEW_REL, SLOTS, START_DATE,
                    World)


AUCTION_SIGMA = 0.30    # spread of the competitor bid level across auctions within a daypart


def _slot_shares(bid: float, base: dict[int, float], sigma: float) -> dict[int, tuple[float, float]]:
    """Share of auctions won at each slot, and the average CPM paid there.

    Each auction draws one competitor level z ~ LogNormal(0, σ); slot s clears at base[s] · z.
    The bid wins the best slot it meets: slot 1 when z ≤ bid/base[1], slot 5 when
    bid/base[1] < z ≤ bid/base[5], and so on. It pays that slot's clearing price. Raising a bid
    therefore wins the top slot more often but pays more for the marginal auctions it wins."""
    out, lo = {}, 0.0
    e = np.exp(sigma ** 2 / 2)
    for s in SLOTS:
        hi = bid / base[s]
        p_hi = norm.cdf(np.log(hi) / sigma)
        p_lo = norm.cdf(np.log(lo) / sigma) if lo > 0 else 0.0
        share = max(p_hi - p_lo, 0.0)
        if share > 1e-6:
            pe_hi = norm.cdf(np.log(hi) / sigma - sigma)
            pe_lo = norm.cdf(np.log(lo) / sigma - sigma) if lo > 0 else 0.0
            cpm = base[s] * e * (pe_hi - pe_lo) / share
        else:
            cpm = base[s]
        out[s] = (share, cpm)
        lo = max(lo, hi)
    return out


class Market:
    def __init__(self, world: World):
        self.w = world
        p = world.public
        self.cities = p["cities"].set_index("city_id")
        self.products = p["products"].set_index("sku_id")
        self.keywords = p["keywords"].set_index("keyword_id")
        self.ks = p["keyword_sku"].set_index(["sku_id", "keyword_id"])
        self.sku_city = p["sku_city"].set_index(["sku_id", "city_id"])
        self.city_ids = list(self.cities.index)
        self.kw_ids = list(self.keywords.index)
        self.sku_ids = list(self.products.index)
        # fixed index of every campaign × keyword pair that can ever exist
        ck = p["campaign_keywords"].merge(p["campaigns"][["campaign_id", "sku_id", "city_id"]])
        self.pairs = list(ck[["campaign_id", "keyword_id", "sku_id", "city_id"]].itertuples(index=False, name=None))
        self.camp_ids = list(p["campaigns"].campaign_id)

    # ── random draws, fixed shapes per day ────────────────────────────────────
    def _draws(self, day: int) -> dict:
        rng = np.random.default_rng(np.random.SeedSequence([self.w.seed, 1009, day]))
        nc, nk, nd, ns = len(self.city_ids), len(self.kw_ids), len(DAYPARTS), len(SLOTS)
        n = self.w.truth["noise"]
        return {
            "search": np.exp(rng.normal(0, n["searches_sigma"], (nc, nk, nd))),
            "price": np.exp(rng.normal(0, n["price_sigma"], (nc, nk, nd))),
            "organic": np.exp(rng.normal(0, n["organic_sigma"], (len(self.sku_ids), nc))),
            "u_ad": rng.uniform(size=(len(self.pairs), nd, ns)),
            "u_org": rng.uniform(size=(len(self.sku_ids), nc)),
            "u_can": rng.uniform(size=(len(self.sku_ids), nc)),
        }

    def _shock(self, kind: str, day: int, **match) -> float | None:
        out = None
        for s in self.w.truth["shocks"]:
            if s["kind"] != kind or day < s["from_day"] or day > s.get("to_day", 10**9):
                continue
            if "city_id" in s and match.get("city_id") not in (None, s["city_id"]):
                continue
            if "sku_id" in s and match.get("sku_id") != s["sku_id"]:
                continue
            if "keyword_ids" in s and match.get("keyword_id") not in s["keyword_ids"]:
                continue
            out = s.get("mult", s.get("osa"))
        return out

    def osa(self, sku: str, city: str, day: int) -> float:
        shock = self._shock("osa", day, sku_id=sku, city_id=city)
        return float(shock if shock is not None else self.sku_city.loc[(sku, city), "base_osa"])

    # ── one day ───────────────────────────────────────────────────────────────
    def simulate_day(self, day: int, campaigns: pd.DataFrame, campaign_keywords: pd.DataFrame) -> dict[str, pd.DataFrame]:
        t = self.w.truth
        dr = self._draws(day)
        dt = START_DATE + timedelta(days=day)
        weekend = t["noise"]["weekend_lift"] if dt.weekday() >= 5 else 1.0

        camp = campaigns.set_index("campaign_id")
        bids = campaign_keywords.set_index(["campaign_id", "keyword_id"])
        remaining = {cid: float(camp.loc[cid, "daily_budget_inr"]) for cid in self.camp_ids}
        ran_out_dp: dict[str, str] = {}
        ci = {c: i for i, c in enumerate(self.city_ids)}
        ki = {k: i for i, k in enumerate(self.kw_ids)}
        osa = {(s, c): self.osa(s, c, day) for s in self.sku_ids for c in self.city_ids}

        facts = []
        for d, dp in enumerate(DAYPARTS):
            # 1–2. who bids, what each slot clears at, who wins which slot
            by_market: dict[tuple[str, str], list[tuple[float, int]]] = {}
            for pi, (cid, kid, sku, city) in enumerate(self.pairs):
                row = camp.loc[cid]
                if not row[f"on_{dp}"] or remaining[cid] <= 0.5:
                    continue
                if (cid, kid) not in bids.index or not bool(bids.loc[(cid, kid), "active"]):
                    continue
                by_market.setdefault((city, kid), []).append((float(bids.loc[(cid, kid), "bid_cpm_inr"]), pi))

            demand: dict[int, list] = {}
            for (city, kid), entrants in by_market.items():
                c, k = self.cities.loc[city], self.keywords.loc[kid]
                kt = t["keywords"][kid]
                searches = (k.searches_30d / 30 * c.demand_share * c[f"share_{dp}"]
                            * t["city_kw_affinity"][(city, kid)] * weekend * dr["search"][ci[city], ki[kid], d]
                            * (self._shock("demand", day, keyword_id=kid) or 1.0))
                pmult = self._shock("price", day, city_id=city, keyword_id=kid) or 1.0
                level = dr["price"][ci[city], ki[kid], d]
                base = {s: k.rank1_cpm_inr * c.cpm_index * DAYPART_PRICE[d] * SLOT_PRICE_REL[s] * kt["price_dev"][s]
                        * level * pmult for s in SLOTS}
                occupied = {s: 0.0 for s in SLOTS}          # share of auctions a higher Aurel bid already holds
                for bid, pi in sorted(entrants, key=lambda x: -x[0]):
                    shares = _slot_shares(bid, base, AUCTION_SIGMA)
                    # own-brand collision: where a sibling already holds the slot, this ad drops one slot down
                    moved, adj = 0.0, {}
                    for s in SLOTS:
                        p_s, cpm_s = shares[s]
                        p_s += moved
                        keep = p_s * (1 - occupied[s])
                        moved = p_s - keep
                        adj[s] = (keep, cpm_s)
                    for s in SLOTS:
                        occupied[s] = min(1.0, occupied[s] + adj[s][0])
                    _cid, _kid, sku, _city = self.pairs[pi]
                    rows = []
                    for s in SLOTS:
                        share, cpm = adj[s]
                        if share <= 1e-4:
                            continue
                        impr = searches * share * SLOT_VIEW_REL[s] * kt["view_dev"][s] * osa[(sku, city)]
                        rows.append((s, impr, cpm))
                    if rows:
                        demand[pi] = rows

            # 4. budget pacing within the daypart
            want: dict[str, float] = {}
            for pi, rows in demand.items():
                want[self.pairs[pi][0]] = want.get(self.pairs[pi][0], 0.0) + sum(i * c / 1000 for _, i, c in rows)
            frac = {}
            for cid, w in want.items():
                if w > remaining[cid]:
                    frac[cid] = remaining[cid] / w
                    ran_out_dp.setdefault(cid, dp)
                else:
                    frac[cid] = 1.0
            for cid, w in want.items():
                remaining[cid] -= w * frac[cid]

            # 5. ad orders
            for pi, rows in demand.items():
                cid, kid, sku, city = self.pairs[pi]
                kt = t["keywords"][kid]
                asp = float(self.products.loc[sku, "asp_inr"])
                for slot, impr, cpm in rows:
                    impr *= frac[cid]
                    if impr < 1:
                        continue
                    lam = (impr * SLOT_CONV[slot] * kt["conv_dev"][slot] * kt["intent"]
                           * self.ks.loc[(sku, kid), "relevance"] * t["appeal"][sku])
                    orders = int(poisson.ppf(dr["u_ad"][pi, d, SLOTS.index(slot)], lam)) if lam > 0 else 0
                    facts.append({"day": day, "date": dt.isoformat(), "campaign_id": cid, "sku_id": sku,
                                  "city_id": city, "keyword_id": kid, "daypart": dp, "slot": slot,
                                  "impressions": round(impr), "spend_inr": round(impr * cpm / 1000, 2),
                                  "ad_orders": orders, "ad_revenue_inr": round(orders * asp, 2)})

        facts_df = pd.DataFrame(facts, columns=["day", "date", "campaign_id", "sku_id", "city_id", "keyword_id",
                                                "daypart", "slot", "impressions", "spend_inr", "ad_orders",
                                                "ad_revenue_inr"])

        # campaign pacing
        spend_by_c = facts_df.groupby("campaign_id").spend_inr.sum() if len(facts_df) else pd.Series(dtype=float)
        camp_rows = []
        for cid in self.camp_ids:
            camp_rows.append({"day": day, "date": dt.isoformat(), "campaign_id": cid,
                              "daily_budget_inr": float(camp.loc[cid, "daily_budget_inr"]),
                              "spend_inr": round(float(spend_by_c.get(cid, 0.0)), 2),
                              "ran_out": cid in ran_out_dp, "ran_out_daypart": ran_out_dp.get(cid, "")})

        # 6. organic + total offtake per SKU × city
        sc_rows = []
        for si, sku in enumerate(self.sku_ids):
            p = self.products.loc[sku]
            for cj, city in enumerate(self.city_ids):
                c = self.cities.loc[city]
                lam_org = p.organic_units_per_day * c.demand_share * weekend * dr["organic"][si, cj] * osa[(sku, city)]
                organic_base = int(poisson.ppf(dr["u_org"][si, cj], lam_org)) if lam_org > 0 else 0
                ad = facts_df[(facts_df.sku_id == sku) & (facts_df.city_id == city)]
                ad_units = int(ad.ad_orders.sum())
                cannibal = 0.0
                for r in ad.itertuples():
                    inc = t["keywords"][r.keyword_id]["incrementality"] * t["organic_damp"].get((sku, r.keyword_id), 1.0)
                    cannibal += (1 - inc) * r.ad_orders
                cannibal = int(np.floor(cannibal + dr["u_can"][si, cj]))
                organic = max(organic_base - cannibal, 0)
                total = organic + ad_units
                sc_rows.append({"day": day, "date": dt.isoformat(), "sku_id": sku, "city_id": city,
                                "osa": round(osa[(sku, city)], 3), "ad_units": ad_units, "organic_units": organic,
                                "total_units": total, "offtake_inr": round(total * p.asp_inr, 2),
                                "ad_revenue_inr": round(ad_units * p.asp_inr, 2)})
        return {"daily_facts": facts_df, "campaign_daily": pd.DataFrame(camp_rows),
                "sku_city_daily": pd.DataFrame(sc_rows)}
