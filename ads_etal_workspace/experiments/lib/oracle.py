"""Truth-side measurement: the quantities a policy cannot observe. Offline tooling only — this
module reads `World.truth` and `gpc.market` internals, which `harness/` must never do.

Three things live here:

1. `day_potential` re-derives, for one simulated day, the **searches** per (city, keyword, daypart)
   and the **potential impressions** per (campaign, keyword, daypart, slot): what the auction would
   serve if no campaign hit its budget. It replicates `Market.simulate_day`'s auction block
   (searches, clearing prices, `_slot_shares`, own-brand collision) using the market's own random
   draws, so it is checked against emitted data in `x0_measurement` (X0.2).
2. `true_incremental` turns emitted ad orders into true incremental units using the hidden
   keyword incrementality and organic damping.
3. `week_states` rebuilds the campaign/bid state that was live in each simulated week from a
   `SimResult`, so (1) can be evaluated against the state that was actually in force.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from gpc.market import Market, _slot_shares
from gpc.runner import apply_actions
from gpc.world import (DAYPART_PRICE, DAYPARTS, RUN_DAYS, SLOT_PRICE_REL, SLOT_VIEW_REL, SLOTS, START_DATE,
                       WARMUP_DAYS, World)


def day_potential(m: Market, day: int, campaigns: pd.DataFrame, ck: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (searches, potential). `searches`: day, city_id, keyword_id, daypart, searches.
    `potential`: day, campaign_id, keyword_id, daypart, slot, share, impressions_potential.
    Budget truncation is NOT applied, so `impressions_potential` equals emitted impressions only
    on campaign-days that did not run out."""
    t = m.w.truth
    dr = m._draws(day)
    dt = START_DATE + timedelta(days=day)
    weekend = t["noise"]["weekend_lift"] if dt.weekday() >= 5 else 1.0
    camp = campaigns.set_index("campaign_id")
    bids = ck.set_index(["campaign_id", "keyword_id"])
    ci = {c: i for i, c in enumerate(m.city_ids)}
    ki = {k: i for i, k in enumerate(m.kw_ids)}
    osa = {(s, c): m.osa(s, c, day) for s in m.sku_ids for c in m.city_ids}

    s_rows, p_rows = [], []
    for d, dp in enumerate(DAYPARTS):
        by_market: dict[tuple[str, str], list[tuple[float, int]]] = {}
        for pi, (cid, kid, sku, city) in enumerate(m.pairs):
            if not camp.loc[cid, f"on_{dp}"]:
                continue
            if (cid, kid) not in bids.index or not bool(bids.loc[(cid, kid), "active"]):
                continue
            by_market.setdefault((city, kid), []).append((float(bids.loc[(cid, kid), "bid_cpm_inr"]), pi))

        for city in m.city_ids:
            c = m.cities.loc[city]
            for kid in m.kw_ids:
                k = m.keywords.loc[kid]
                searches = (k.searches_30d / 30 * c.demand_share * c[f"share_{dp}"]
                            * t["city_kw_affinity"][(city, kid)] * weekend * dr["search"][ci[city], ki[kid], d]
                            * (m._shock("demand", day, keyword_id=kid) or 1.0))
                s_rows.append({"day": day, "city_id": city, "keyword_id": kid, "daypart": dp,
                               "searches": float(searches)})
                entrants = by_market.get((city, kid))
                if not entrants:
                    continue
                kt = t["keywords"][kid]
                pmult = m._shock("price", day, city_id=city, keyword_id=kid) or 1.0
                level = dr["price"][ci[city], ki[kid], d]
                base = {s: k.rank1_cpm_inr * c.cpm_index * DAYPART_PRICE[d] * SLOT_PRICE_REL[s] * kt["price_dev"][s]
                        * level * pmult for s in SLOTS}
                occupied = {s: 0.0 for s in SLOTS}
                for bid, pi in sorted(entrants, key=lambda x: -x[0]):
                    shares = _slot_shares(bid, base, t["auction_sigma"])
                    moved, adj = 0.0, {}
                    for s in SLOTS:
                        p_s, cpm_s = shares[s]
                        p_s += moved
                        keep = p_s * (1 - occupied[s])
                        moved = p_s - keep
                        adj[s] = (keep, cpm_s)
                    for s in SLOTS:
                        occupied[s] = min(1.0, occupied[s] + adj[s][0])
                    cid, _kid, sku, _city = m.pairs[pi]
                    for s in SLOTS:
                        share, _cpm = adj[s]
                        if share <= 1e-4:
                            continue
                        impr = searches * share * SLOT_VIEW_REL[s] * kt["view_dev"][s] * osa[(sku, city)]
                        p_rows.append({"day": day, "campaign_id": cid, "keyword_id": kid, "daypart": dp,
                                       "slot": s, "share": float(share), "impressions_potential": float(impr)})
    return (pd.DataFrame(s_rows, columns=["day", "city_id", "keyword_id", "daypart", "searches"]),
            pd.DataFrame(p_rows, columns=["day", "campaign_id", "keyword_id", "daypart", "slot", "share",
                                          "impressions_potential"]))


def week_states(world: World, runs: list[dict]) -> dict[int, tuple[pd.DataFrame, pd.DataFrame]]:
    """Day -> (campaigns, campaign_keywords) in force on that day, rebuilt from a SimResult's runs
    (`campaigns_before` + the guardrailed `final` actions, exactly as `gpc.runner.simulate` applied them)."""
    out: dict[int, tuple[pd.DataFrame, pd.DataFrame]] = {}
    camp0, ck0 = world.public["campaigns"], world.public["campaign_keywords"]
    for d in range(WARMUP_DAYS):
        out[d] = (camp0, ck0)
    for r in runs:
        camp, ck = apply_actions(r["campaigns_before"], r["campaign_keywords_before"], r["final"])
        for d in range(r["day"], r["day"] + RUN_DAYS):
            out[d] = (camp, ck)
    return out


def true_incremental(world: World, facts: pd.DataFrame) -> pd.DataFrame:
    """Adds `inc_eff` (true incrementality × organic damping), `incr_units` (ad orders that are
    genuinely new sales) and `cannibalised_units` (ad orders that would have been organic sales
    anyway) to a copy of `daily_facts`. Matches `Market.simulate_day`'s cannibalisation formula
    (before its per-SKU×city×day floor/clip)."""
    t = world.truth
    inc = {k: v["incrementality"] for k, v in t["keywords"].items()}
    damp = t["organic_damp"]
    f = facts.copy()
    f["inc_eff"] = [inc[k] * damp.get((s, k), 1.0) for s, k in zip(f.sku_id, f.keyword_id)]
    f["incr_units"] = f.ad_orders * f.inc_eff
    f["cannibalised_units"] = f.ad_orders - f.incr_units
    return f


def keyword_types(world: World) -> pd.Series:
    return world.public["keywords"].set_index("keyword_id").keyword_type


def clean_mask(world, pot, cd, day):
    """Rows whose whole auction (every sibling in the same city x keyword market) ran without any
    budget truncation that day. A campaign that runs out drops out of later dayparts' auctions, which
    changes its siblings' shares, so excluding only the ran-out campaign's own rows is not enough."""
    ran_out = set(cd[(cd.day == day) & cd.ran_out].campaign_id)
    cc = world.public["campaigns"].set_index("campaign_id").city_id
    tainted = {(cc[c], k) for c in ran_out for k in world.public["campaign_keywords"]
               .query("campaign_id == @c").keyword_id}
    key = list(zip(pot.campaign_id.map(cc), pot.keyword_id))
    return ~pd.Series([k in tainted for k in key], index=pot.index)


def cell_truth(world: World) -> pd.DataFrame:
    """One row per (campaign, keyword) cell with the hidden response parameters: slot-1 conversion
    (orders per impression), true effective incrementality (incrementality x organic damping) and the
    incremental revenue per slot-1 impression (conv x ASP x inc_eff) — the quantity `leader_score`
    tries to estimate."""
    from gpc.world import SLOT_CONV
    t = world.truth
    ks = world.public["keyword_sku"].set_index(["sku_id", "keyword_id"])
    asp = world.public["products"].set_index("sku_id").asp_inr
    ck = world.public["campaign_keywords"].merge(world.public["campaigns"][["campaign_id", "sku_id", "city_id"]])
    rows = []
    for r in ck.itertuples():
        kt = t["keywords"][r.keyword_id]
        conv1 = SLOT_CONV[1] * kt["conv_dev"][1] * kt["intent"] * ks.loc[(r.sku_id, r.keyword_id), "relevance"] * t["appeal"][r.sku_id]
        inc_eff = kt["incrementality"] * t["organic_damp"].get((r.sku_id, r.keyword_id), 1.0)
        rows.append({"campaign_id": r.campaign_id, "keyword_id": r.keyword_id, "sku_id": r.sku_id, "city_id": r.city_id,
                     "conv1": conv1, "inc_eff": inc_eff, "asp": float(asp[r.sku_id]),
                     "true_value_per_impr": conv1 * float(asp[r.sku_id]) * inc_eff})
    return pd.DataFrame(rows)
