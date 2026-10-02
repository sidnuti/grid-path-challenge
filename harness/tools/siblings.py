"""Sibling arbitration (SG3): a market is one city x keyword. Several Aurel campaigns (one SKU
each) can hold cells on the same market and bid against each other for the same auction slot.

Correction carried from the handoff notes: sibling collision does **not** inflate price — clearing
prices come from external competitor bids (see `gpc.market`). A lower-bidding sibling is simply
displaced a slot down (it loses impressions); it never pays more, and it never raises the leader's
price. So the cost of self-competition is not "paying to outbid yourself": it is (a) a futile
follower raise (the grid thinks the extra rupees buy slot 1, but the sibling already holds it —
`G3_TOP_SLOT` blocks this anyway) and (b) a wrong leader, when the SKU holding slot 1 is not the one
with the best value per impression. Two siblings at slots 1 and 5 can add coverage rather than
collide — a market only needs arbitration when more than one sibling is genuinely contesting the
same slot.

`leader_score` = conv (shrunk, slot-1-equivalent) x ASP x ι, i.e. incremental revenue per
impression. The leader is the sibling with the highest score; followers should not chase slot 1 away
from it.
"""

from __future__ import annotations

import pandas as pd

from gpc.observation import Observation

from .incrementality import iota_lookup


def markets(obs: Observation, grid: pd.DataFrame, iota: dict[tuple[str, str], float] | None = None) -> pd.DataFrame:
    """One row per (city_id, keyword_id, campaign_id/sku_id) with slot-1 share, a leader score, and
    whether that sibling is this market's leader."""
    iota = iota or iota_lookup(obs)
    kt = obs.public["keywords"].set_index("keyword_id").keyword_type
    f7 = obs.window("daily_facts", 7)
    camp = obs.campaigns.set_index("campaign_id")
    if len(f7):
        s1 = (f7.assign(s1=f7.impressions.where(f7.slot == 1, 0))
                .groupby(["campaign_id", "keyword_id"]).agg(s1=("s1", "sum"), i=("impressions", "sum")))
        s1["slot1_share"] = s1.s1 / s1.i.replace(0, pd.NA)
    else:
        s1 = pd.DataFrame(columns=["s1", "i", "slot1_share"])

    g1 = grid[grid.slot == 1].drop_duplicates(["campaign_id", "keyword_id"]).set_index(["campaign_id", "keyword_id"])
    rows = []
    for ck in obs.campaign_keywords.itertuples():
        cid, kid = ck.campaign_id, ck.keyword_id
        if cid not in camp.index:
            continue
        sku, city = camp.loc[cid, "sku_id"], camp.loc[cid, "city_id"]
        gkey = (cid, kid)
        conv1 = float(g1.loc[gkey, "orders_day"] / g1.loc[gkey, "impressions_day"]) if gkey in g1.index and g1.loc[gkey, "impressions_day"] > 0 else 0.0
        asp = 0.0
        if gkey in g1.index and conv1 > 0:
            asp = float(g1.loc[gkey, "revenue_day"] / g1.loc[gkey, "orders_day"]) if g1.loc[gkey, "orders_day"] > 0 else 0.0
        t = kt.get(kid, "generic")
        io = iota.get((sku, t), iota.get((sku, "generic"), 0.5))
        score = conv1 * asp * io
        share = float(s1.slot1_share.get((cid, kid), 0.0)) if (cid, kid) in s1.index else 0.0
        rows.append({"city_id": city, "keyword_id": kid, "campaign_id": cid, "sku_id": sku,
                     "slot1_share_7d": round(share, 3), "leader_score": round(score, 4), "iota": io})
    out = pd.DataFrame(rows)
    if not len(out):
        return out
    out["n_siblings"] = out.groupby(["city_id", "keyword_id"]).campaign_id.transform("count")
    out["is_contested"] = out.n_siblings > 1
    out["leader_rank"] = out.groupby(["city_id", "keyword_id"]).leader_score.rank(ascending=False, method="first")
    out["is_leader"] = out.leader_rank == 1
    return out.drop(columns=["leader_rank"])


def contested_markets(mk: pd.DataFrame) -> pd.DataFrame:
    """One row per contested (city_id, keyword_id): the leader and whether a non-leader currently
    holds >= `leader_min_slot1_share` of slot 1 (SG3's "wrong leader" case)."""
    if not len(mk):
        return pd.DataFrame(columns=["city_id", "keyword_id", "n_siblings", "leader_campaign_id",
                                     "leader_slot1_share", "wrong_leader"])
    rows = []
    for (city, kid), g in mk[mk.is_contested].groupby(["city_id", "keyword_id"]):
        leader = g[g.is_leader].iloc[0]
        wrong = bool(((g.slot1_share_7d >= 0.80) & (~g.is_leader)).any())
        rows.append({"city_id": city, "keyword_id": kid, "n_siblings": int(g.n_siblings.iloc[0]),
                     "leader_campaign_id": leader.campaign_id, "leader_slot1_share": leader.slot1_share_7d,
                     "wrong_leader": wrong})
    return pd.DataFrame(rows)


def followers_to_hold(mk: pd.DataFrame, min_slot1_share: float = 0.80) -> set[tuple[str, str]]:
    """(campaign_id, keyword_id) pairs that should not be raised: a sibling already holds >= 80%
    of slot 1 on that market and this cell is not the leader."""
    if not len(mk):
        return set()
    out = set()
    for (city, kid), g in mk[mk.is_contested].groupby(["city_id", "keyword_id"]):
        if (g.slot1_share_7d >= min_slot1_share).any():
            for r in g[~g.is_leader].itertuples():
                out.add((r.campaign_id, r.keyword_id))
    return out
