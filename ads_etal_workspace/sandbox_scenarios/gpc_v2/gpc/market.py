"""The hidden market simulator. Turns a campaign configuration into one day of observed data.

Policies never import this module. They see only what it emits (daily facts, campaign pacing,
SKU × city offtake), exactly as an operator would see platform reports.

Mechanics, per day and daypart (night → morning → afternoon → evening):

1. Searches = 30-day volume / 30 × city share × daypart share × city-keyword affinity
   × weekend lift × noise × any demand shock.
2. Auction: each slot (1 / 5 / 9 / 13) has a median clearing CPM = rank-1 CPM × city index
   × daypart level × slot price ratio × daily noise × any price shock. Competitor bids vary from
   auction to auction (log-normal; the spread is a hidden scenario parameter), so a bid wins a SHARE of auctions at each slot and
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
from scipy import special
from scipy.stats import poisson

from .calendar import Calendar
from .competitors import Competitors
from .intent import Intent
from .shelf import decompose
from .stock import Stock
from .world import (DAYPART_PRICE, DAYPARTS, SLOT_CONV, SLOT_PRICE_REL, SLOT_VIEW_REL, SLOTS, START_DATE,
                    World)


DECOMP_COLUMNS = ["day", "campaign_id", "sku_id", "city_id", "keyword_id", "daypart", "slot", "ad_orders",
                  "self", "sibling", "competitor", "expansion", "excess"]


def _ndtr(x):
    """`scipy.stats.norm.cdf` for a finite scalar: the same `special.ndtr` kernel, without the argument machinery."""
    return special.ndtr(x)


def _poisson_ppf(q, mu) -> float:
    """`scipy.stats.poisson.ppf(q, mu)` for scalars, bit-identical (scipy 1.17 `poisson_gen._ppf`), ~50x faster."""
    if 0 < q < 1 and mu >= 0:
        vals = np.ceil(special.pdtrik(q, mu))
        vals1 = max(vals - 1, 0)
        return vals1 if special.pdtr(vals1, mu) >= q else vals
    return poisson.ppf(q, mu)


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
        p_hi = _ndtr(np.log(hi) / sigma)
        p_lo = _ndtr(np.log(lo) / sigma) if lo > 0 else 0.0
        share = max(p_hi - p_lo, 0.0)
        if share > 1e-6:
            pe_hi = _ndtr(np.log(hi) / sigma - sigma)
            pe_lo = _ndtr(np.log(lo) / sigma - sigma) if lo > 0 else 0.0
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
        # plain-dict views of the static tables (pandas .loc in the inner loops was ~40% of run time)
        self._city = {c: r for c, r in zip(self.city_ids, self.cities.to_dict("records"))}
        self._kw = {k: r for k, r in zip(self.kw_ids, self.keywords.to_dict("records"))}
        self._prod = {s: r for s, r in zip(self.sku_ids, self.products.to_dict("records"))}
        self._rel = {k: float(v) for k, v in self.ks["relevance"].items()}
        self._base_osa = {k: float(v) for k, v in self.sku_city["base_osa"].items()}
        # sim v2 modules (absent in legacy scenarios). Stateful parts live on this instance, so the policy run
        # and the ads-off counterfactual each keep their own stock and competitor state.
        tr = world.truth
        self.cal = Calendar(tr["calendar"]) if tr.get("calendar") else None
        self.stock = Stock(tr["calendar"].get("ephemeral_skus", [])) if self.cal else None
        self.comp = Competitors(tr["competitors"], self.cal or Calendar({}), self.city_ids) if tr.get("competitors") else None
        self.intent = Intent(tr["intent"], tr["intent_mix"]) if tr.get("intent_mix") else None
        self._org_w: dict[str, list[tuple[str, float]]] = {}      # organic multiplier weights: searches × relevance
        for (sk, kid), r in self._rel.items():
            self._org_w.setdefault(sk, []).append((kid, self._kw[kid]["searches_30d"] * r))

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
        if self.stock is not None and self.stock.tracks(sku):
            if not self.cal.is_live(sku, day) or not self.stock.available(sku, city):
                return 0.0
        return float(shock if shock is not None else self._base_osa[(sku, city)])

    def organic_mult(self, sku: str, day: int) -> float:
        ws = self._org_w.get(sku)
        if self.cal is None or not ws:
            return 1.0
        tot = sum(w for _, w in ws)
        return sum(w * self.cal.search_mult(k, day) for k, w in ws) / tot

    def _searches(self, city: str, kid: str, d: int, dp: str, day: int, weekend: float, dr: dict, ci, ki) -> float:
        c, k = self._city[city], self._kw[kid]
        return (k["searches_30d"] / 30 * c["demand_share"] * c[f"share_{dp}"]
                * self.w.truth["city_kw_affinity"][(city, kid)] * weekend * dr["search"][ci[city], ki[kid], d]
                * (self._shock("demand", day, keyword_id=kid) or 1.0))

    # ── one day ───────────────────────────────────────────────────────────────
    def simulate_day(self, day: int, campaigns: pd.DataFrame, campaign_keywords: pd.DataFrame) -> dict[str, pd.DataFrame]:
        t = self.w.truth
        shelves = t.get("shelves")
        row_split: list[dict | None] = []          # per fact row, aligned with `facts` (shelf model only)
        dr = self._draws(day)
        dt = START_DATE + timedelta(days=day)
        weekend = t["noise"]["weekend_lift"] if dt.weekday() >= 5 else 1.0

        camp = {r["campaign_id"]: r for r in campaigns.to_dict("records")}
        bids = {(r["campaign_id"], r["keyword_id"]): r for r in campaign_keywords.to_dict("records")}
        remaining = {cid: float(camp[cid]["daily_budget_inr"]) for cid in self.camp_ids}
        ran_out_dp: dict[str, str] = {}
        ci = {c: i for i, c in enumerate(self.city_ids)}
        ki = {k: i for i, k in enumerate(self.kw_ids)}
        osa = {(s, c): self.osa(s, c, day) for s in self.sku_ids for c in self.city_ids}

        facts = []
        s1_day: dict[str, float] = {}            # sim v2 competitors: Aurel slot-1 share on the brand query, by city
        conq_sc: dict[tuple[str, str], float] = {}
        conq_rows: list[dict] = []
        slot1_rows: list[dict] = []
        for d, dp in enumerate(DAYPARTS):
            # 1–2. who bids, what each slot clears at, who wins which slot
            by_market: dict[tuple[str, str], list[tuple[float, int]]] = {}
            for pi, (cid, kid, sku, city) in enumerate(self.pairs):
                row = camp[cid]
                if not row[f"on_{dp}"] or remaining[cid] <= 0.5:
                    continue
                b = bids.get((cid, kid))
                if b is None or not bool(b["active"]):
                    continue
                by_market.setdefault((city, kid), []).append((float(b["bid_cpm_inr"]), pi))

            demand: dict[int, list] = {}
            markets: dict[tuple[str, str], tuple[float, list[int]]] = {}     # sim v2 shelf: searches and entrants
            # stage 1: auction outcome per market (independent of search volume)
            stage: dict[tuple[str, str], tuple] = {}
            for (city, kid), entrants in by_market.items():
                c, k = self._city[city], self._kw[kid]
                kt = t["keywords"][kid]
                pmult = self._shock("price", day, city_id=city, keyword_id=kid) or 1.0
                if self.comp is not None:
                    pmult *= self.comp.price_mult(kid, city)
                level = dr["price"][ci[city], ki[kid], d]
                base = {s: k["rank1_cpm_inr"] * c["cpm_index"] * DAYPART_PRICE[d] * SLOT_PRICE_REL[s] * kt["price_dev"][s]
                        * level * pmult for s in SLOTS}
                occupied = {s: 0.0 for s in SLOTS}          # share of auctions a higher Aurel bid already holds
                won = []
                for bid, pi in sorted(entrants, key=lambda x: -x[0]):
                    shares = _slot_shares(bid, base, t["auction_sigma"])
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
                    won.append((pi, adj))
                    if shelves is not None:            # truth: share of auctions won at slot 1 (G-1 objective f2)
                        slot1_rows.append({"day": day, "city_id": city, "keyword_id": kid, "daypart": dp,
                                           "sku_id": self.pairs[pi][2], "share1": adj[1][0]})
                stage[(city, kid)] = (won, occupied)
                if self.comp is not None and kid == self.comp.opp_kw:
                    s1_day[city] = s1_day.get(city, 0.0) + occupied[1] * c[f"share_{dp}"]

            # sim v2 intent: reformulation from generic queries to the brand query (needs Aurel visibility first)
            reform: dict[str, float] = {}
            conv_boost: dict[tuple[str, str], float] = {}
            if self.intent is not None and self.intent.reform_from:
                for city in self.city_ids:
                    for kid in self.intent.reform_from:
                        if kid not in shelves:
                            continue
                        w_ad = {}
                        for pi, adj in stage.get((city, kid), ([], None))[0]:
                            sku = self.pairs[pi][2]
                            kt = t["keywords"][kid]
                            w_ad[sku] = sum(adj[s][0] * SLOT_VIEW_REL[s] * kt["view_dev"][s] for s in SLOTS) * osa[(sku, city)]
                        sq = self._searches(city, kid, d, dp, day, weekend, dr, ci, ki)
                        if self.cal is not None:
                            sq *= self.cal.search_mult(kid, day)
                        vis = self.intent.aurel_visibility(shelves[kid], w_ad)
                        reform[city] = reform.get(city, 0.0) + self.intent.reformulation_searches(kid, city, sq, vis)

            # stage 2: searches and impressions
            for (city, kid), (won, occupied) in stage.items():
                kt = t["keywords"][kid]
                searches = self._searches(city, kid, d, dp, day, weekend, dr, ci, ki)
                if self.cal is not None:
                    searches *= self.cal.search_mult(kid, day)
                if reform and kid == self.intent.brand_query:
                    extra = reform.get(city, 0.0)
                    searches += extra
                    if searches > 0:                   # conversion boost on the brand query, by reformulated share
                        conv_boost[(city, kid)] = 1 + (self.intent.reform_conv - 1) * extra / searches
                if self.cal is not None and searches <= 0:     # keyword not live today (ephemeral)
                    continue
                for pi, adj in won:
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
                        markets.setdefault((city, kid), (searches, []))[1].append(pi)

            # sim v2 intent: Aurel-loyal shoppers stolen by competitor ads on Aurel-owned queries
            if self.comp is not None and self.intent is not None:
                for kid in self.comp.conquest_keywords():
                    for city in self.city_ids:
                        kappa = self.comp.conquest(kid, city)
                        if kappa <= 0:
                            continue
                        won, occupied = stage.get((city, kid), ([], {1: 0.0}))
                        sq = self._searches(city, kid, d, dp, day, weekend, dr, ci, ki)
                        if self.cal is not None:
                            sq *= self.cal.search_mult(kid, day)
                        if reform and kid == self.intent.brand_query:
                            sq += reform.get(city, 0.0)
                        lost = self.intent.conquest_loss(kid, city, sq, kappa, occupied[1])
                        if lost <= 0:
                            continue
                        sh = shelves[kid]
                        w_ad = {self.pairs[pi][2]: sum(adj[s][0] * SLOT_VIEW_REL[s] for s in SLOTS) for pi, adj in won}
                        wa = np.array([w_ad.get(it, 0.0) for it in sh.items])
                        share = self.intent._aurel_shares(sh, wa)
                        for j, it in enumerate(sh.items):
                            if share[j] > 0:
                                conq_sc[(it, city)] = conq_sc.get((it, city), 0.0) + lost * share[j]
                        conq_rows.append({"day": day, "city_id": city, "keyword_id": kid, "daypart": dp,
                                          "kappa": kappa, "aurel_slot1": occupied[1], "lost_units": lost})

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

            # sim v2 shelf: split of each ad order into self / sibling / competitor / expansion, per auction
            dec: dict[int, dict] = {}
            if shelves is not None:
                for (city, kid), (searches, pis) in markets.items():
                    w_ad = {}
                    for pi in pis:
                        cid = self.pairs[pi][0]
                        w_ad[self.pairs[pi][2]] = sum(i * frac[cid] for _, i, _ in demand[pi] if i * frac[cid] >= 1) / searches
                    split = (self.intent.decompose(shelves[kid], w_ad, city) if self.intent is not None
                             else decompose(shelves[kid], w_ad))
                    for pi in pis:
                        if self.pairs[pi][2] in split:
                            dec[pi] = split[self.pairs[pi][2]]

            # 5. ad orders
            for pi, rows in demand.items():
                cid, kid, sku, city = self.pairs[pi]
                kt = t["keywords"][kid]
                asp = float(self._prod[sku]["asp_inr"])
                for slot, impr, cpm in rows:
                    impr *= frac[cid]
                    if impr < 1:
                        continue
                    lam = (impr * SLOT_CONV[slot] * kt["conv_dev"][slot] * kt["intent"]
                           * self._rel[(sku, kid)] * t["appeal"][sku])
                    if self.cal is not None and dp == "evening":
                        lam *= self.cal.evening_lift(day)
                    if conv_boost:
                        lam *= conv_boost.get((city, kid), 1.0)
                    orders = int(_poisson_ppf(dr["u_ad"][pi, d, SLOTS.index(slot)], lam)) if lam > 0 else 0
                    facts.append({"day": day, "date": dt.isoformat(), "campaign_id": cid, "sku_id": sku,
                                  "city_id": city, "keyword_id": kid, "daypart": dp, "slot": slot,
                                  "impressions": round(impr), "spend_inr": round(impr * cpm / 1000, 2),
                                  "ad_orders": orders, "ad_revenue_inr": round(orders * asp, 2)})
                    if shelves is not None:
                        row_split.append(dec.get(pi))

        facts_df = pd.DataFrame(facts, columns=["day", "date", "campaign_id", "sku_id", "city_id", "keyword_id",
                                                "daypart", "slot", "impressions", "spend_inr", "ad_orders",
                                                "ad_revenue_inr"])

        # campaign pacing
        spend_by_c = facts_df.groupby("campaign_id").spend_inr.sum() if len(facts_df) else pd.Series(dtype=float)
        camp_rows = []
        for cid in self.camp_ids:
            camp_rows.append({"day": day, "date": dt.isoformat(), "campaign_id": cid,
                              "daily_budget_inr": float(camp[cid]["daily_budget_inr"]),
                              "spend_inr": round(float(spend_by_c.get(cid, 0.0)), 2),
                              "ran_out": cid in ran_out_dp, "ran_out_daypart": ran_out_dp.get(cid, "")})

        # 6. organic + total offtake per SKU × city
        # ad units and "would have bought anyway" units per SKU × city, summed in fact-row order (same float sums as before)
        ad_units_sc: dict[tuple[str, str], int] = {}
        cannibal_sc: dict[tuple[str, str], float] = {}
        decomp_rows = []
        for n, f in enumerate(facts):
            key = (f["sku_id"], f["city_id"])
            ad_units_sc[key] = ad_units_sc.get(key, 0) + f["ad_orders"]
            if shelves is None:
                inc = t["keywords"][f["keyword_id"]]["incrementality"] * t["organic_damp"].get((f["sku_id"], f["keyword_id"]), 1.0)
                cannibal_sc[key] = cannibal_sc.get(key, 0.0) + (1 - inc) * f["ad_orders"]
                continue
            sp = row_split[n] or {"self": 1.0, "sibling": {}, "competitor": 0.0, "expansion": 0.0, "excess": 0.0}
            o = f["ad_orders"]
            cannibal_sc[key] = cannibal_sc.get(key, 0.0) + sp["self"] * o
            for sib, fr in sp["sibling"].items():                 # orders the sibling would have had organically
                k2 = (sib, f["city_id"])
                cannibal_sc[k2] = cannibal_sc.get(k2, 0.0) + fr * o
            decomp_rows.append({"day": day, "campaign_id": f["campaign_id"], "sku_id": f["sku_id"],
                                "city_id": f["city_id"], "keyword_id": f["keyword_id"], "daypart": f["daypart"],
                                "slot": f["slot"], "ad_orders": o, "self": sp["self"] * o,
                                "sibling": sum(sp["sibling"].values()) * o, "competitor": sp["competitor"] * o,
                                "expansion": sp["expansion"] * o, "excess": sp["excess"] * o})
        for key, v in conq_sc.items():                       # sim v2: conquest losses come out of organic sales
            cannibal_sc[key] = cannibal_sc.get(key, 0.0) + v
        sc_rows, stock_rows = [], []
        for si, sku in enumerate(self.sku_ids):
            p = self._prod[sku]
            for cj, city in enumerate(self.city_ids):
                c = self._city[city]
                lam_org = p["organic_units_per_day"] * c["demand_share"] * weekend * dr["organic"][si, cj] * osa[(sku, city)]
                if self.cal is not None:
                    lam_org *= self.organic_mult(sku, day)
                organic_base = int(_poisson_ppf(dr["u_org"][si, cj], lam_org)) if lam_org > 0 else 0
                ad_units = int(ad_units_sc.get((sku, city), 0))
                cannibal = int(np.floor(cannibal_sc.get((sku, city), 0.0) + dr["u_can"][si, cj]))
                organic = max(organic_base - cannibal, 0)
                if self.stock is not None and self.stock.tracks(sku) and self.cal.is_live(sku, day):
                    ad_units, organic, before, after = self.stock.fulfil(sku, city, ad_units, organic)
                    stock_rows.append({"day": day, "sku_id": sku, "city_id": city, "stock_start": before,
                                       "sold": ad_units + organic, "stock_end": after})
                total = organic + ad_units
                sc_rows.append({"day": day, "date": dt.isoformat(), "sku_id": sku, "city_id": city,
                                "osa": round(osa[(sku, city)], 3), "ad_units": ad_units, "organic_units": organic,
                                "total_units": total, "offtake_inr": round(total * p["asp_inr"], 2),
                                "ad_revenue_inr": round(ad_units * p["asp_inr"], 2)})
        out = {"daily_facts": facts_df, "campaign_daily": pd.DataFrame(camp_rows),
               "sku_city_daily": pd.DataFrame(sc_rows)}
        if shelves is not None:                # truth-side table; the runner keeps it out of observations
            out["truth_decomp"] = pd.DataFrame(decomp_rows, columns=DECOMP_COLUMNS)
            out["truth_slot1"] = pd.DataFrame(slot1_rows, columns=["day", "city_id", "keyword_id", "daypart", "sku_id",
                                                                   "share1"])
        if self.stock is not None:             # the brand knows its own stock: public
            out["pub_stock_daily"] = pd.DataFrame(stock_rows, columns=["day", "sku_id", "city_id", "stock_start", "sold",
                                                                       "stock_end"])
        if self.comp is not None:
            out["truth_conquest"] = pd.DataFrame(conq_rows, columns=["day", "city_id", "keyword_id", "daypart", "kappa",
                                                                     "aurel_slot1", "lost_units"])
            out["truth_competitors"] = pd.DataFrame(
                [{"day": day, "agent": a, "bid_level": b} for a, b in self.comp.bid.items()]
                + [{"day": day, "agent": f"conquest_{c}", "bid_level": float(on)} for c, on in self.comp.on.items()])
            self.comp.end_of_day(day, s1_day)
        return out
