"""Track-A decision vector → campaign set-up (design/04 §2.1–2.2), a pure function of (x, observation).

x ∈ [0, 1]^d. Dimensions (names are what the LLM sees in MoHOLLM's prompt):

  bid_brand, bid_generic, bid_competition   bid multiplier by keyword type      0.5–1.5 × starting bid
  bid_bar, bid_liquid                       bid multiplier by nest              0.7–1.3
  share_north, share_west_of_rest           region budget shares by stick-breaking (2 dims for 3 regions):
                                            North = s1, West = (1 − s1)·s2, South = the rest
  daypart                                   < 1/3 night off · < 2/3 all dayparts · else evening and afternoon only
  festive                                   gift-pack S6 and "bath gift set" K11 cells: 0–2 × base bid and S6 budget,
                                            applied only in runs that overlap the live window
  defend_threshold                          raise K01 bids ×1.5 in a city whose conquest signal exceeds this
  budget_scale (E2/E3 only)                 0.8–1.2 × B per day

Deviations from doc 04 §2.1 (logs/P3_log.md):
  - stick-breaking over 3 regions needs 2 dimensions, not 3;
  - bids anchor to the *starting* (warm-up) bids, not the live bid: re-decoding "× live bid" every run would
    compound (1.5^6 ≈ 11× by run 6). The policy is stationary in x and adapts only through observations
    (live window, conquest signal);
  - E1 fixes the daily budget at B/day = warm-up spend per day (Spend ≤ B; budgets are caps), so budget_scale
    exists only for E2/E3;
  - the simulator has no per-daypart bid modifier, so the daypart tilt is a 3-level schedule.

The conquest signal is observable: K01's slot-1 clearing CPM over the last 7 days relative to warm-up,
(ratio − 1)/0.25 clipped to [0, 1]. With no slot-1 K01 impressions last week it is 1 (unknown ⇒ suspect).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from gpc.world import DAYPARTS, RUN_DAYS, WARMUP_DAYS

BASE_DIMS = ["bid_brand", "bid_generic", "bid_competition", "bid_bar", "bid_liquid", "share_north",
             "share_west_of_rest", "daypart", "festive", "defend_threshold"]
REGION = {"DEL": "north", "MUM": "west", "PUN": "west", "BLR": "south", "HYD": "south"}
NEST = {"Soap": "bar", "Kids Soap": "bar", "Body Wash": "liquid", "Shower Gel": "liquid"}
BID_FLOOR, BID_CEIL = 200.0, 10_000.0
DEFEND_MULT = 1.5
CONQUEST_CPM_SCALE = 0.25


@dataclass(frozen=True)
class Encoding:
    budget_scale: bool = False

    @property
    def dims(self) -> list[str]:
        return BASE_DIMS + (["budget_scale"] if self.budget_scale else [])

    @property
    def d(self) -> int:
        return len(self.dims)

    def as_dict(self, x) -> dict[str, float]:
        x = np.asarray(x, dtype=float)
        assert x.shape == (self.d,), f"expected {self.d} dims, got {x.shape}"
        assert np.all((x >= -1e-12) & (x <= 1 + 1e-12)), "x must lie in [0, 1]^d"
        return dict(zip(self.dims, np.clip(x, 0, 1)))


def region_shares(v: dict[str, float]) -> dict[str, float]:
    n = v["share_north"]
    w = (1 - n) * v["share_west_of_rest"]
    return {"north": n, "west": w, "south": 1 - n - w}


def dayparts_for(level: float) -> list[str]:
    if level < 1 / 3:
        return [dp for dp in DAYPARTS if dp != "night"]
    if level < 2 / 3:
        return list(DAYPARTS)
    return ["afternoon", "evening"]


def conquest_signal(obs) -> dict[str, float]:
    f = obs.daily_facts
    k01 = f[(f.keyword_id == "K01") & (f.slot == 1)]
    warm = k01[k01.day < WARMUP_DAYS]
    last = k01[k01.day >= obs.day - 7]
    out = {}
    for c in obs.public["cities"].city_id:
        w, l = warm[warm.city_id == c], last[last.city_id == c]
        if l.impressions.sum() <= 0 or w.impressions.sum() <= 0:
            out[c] = 1.0
            continue
        r = (l.spend_inr.sum() / l.impressions.sum()) / (w.spend_inr.sum() / w.impressions.sum())
        out[c] = float(np.clip((r - 1) / CONQUEST_CPM_SCALE, 0, 1))
    return out


def _live_overlap(obs, entity: str) -> bool | None:
    cal = obs.public.get("calendar_public")
    if cal is None:
        return None
    row = cal[cal.id == entity]
    if not len(row):
        return None
    lo, hi = int(row.from_day.iloc[0]), int(row.to_day.iloc[0])
    return lo <= obs.day + RUN_DAYS - 1 and obs.day <= hi


def warmup_spend_per_day(obs) -> float:
    f = obs.daily_facts
    return float(f[f.day < WARMUP_DAYS].spend_inr.sum() / WARMUP_DAYS)


def decode(x, obs, enc: Encoding = Encoding()) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(campaigns, campaign_keywords) to run for the next 7 days. Pure: same (x, obs) ⇒ same set-up."""
    v = enc.as_dict(x)
    pub = obs.public
    kt = pub["keywords"].set_index("keyword_id").keyword_type
    nest = pub["products"].set_index("sku_id").sub_category.map(NEST)
    start_ck = pub["campaign_keywords"].merge(pub["campaigns"][["campaign_id", "sku_id", "city_id"]])
    ephemeral = set(pub["calendar_public"].id) if "calendar_public" in pub else set()
    signal = conquest_signal(obs)

    type_mult = {"brand": 0.5 + v["bid_brand"], "generic": 0.5 + v["bid_generic"],
                 "competition": 0.5 + v["bid_competition"]}
    nest_mult = {"bar": 0.7 + 0.6 * v["bid_bar"], "liquid": 0.7 + 0.6 * v["bid_liquid"]}
    fest = 2.0 * v["festive"]

    bids, active = [], []
    for r in start_ck.itertuples():
        b = r.bid_cpm_inr * type_mult[kt[r.keyword_id]] * nest_mult[nest[r.sku_id]]
        on = True
        if r.keyword_id in ephemeral or r.sku_id in ephemeral:
            b *= fest
            on = fest > 0
        if r.keyword_id == "K01" and signal[r.city_id] > v["defend_threshold"]:
            b *= DEFEND_MULT
        bids.append(float(np.clip(round(b, 2), BID_FLOOR, BID_CEIL)))
        active.append(on)
    ck = start_ck[["campaign_id", "keyword_id"]].assign(bid_cpm_inr=bids, active=active)

    camps = pub["campaigns"].copy()
    daily = warmup_spend_per_day(obs) * ((0.8 + 0.4 * v["budget_scale"]) if enc.budget_scale else 1.0)
    shares = region_shares(v)
    # within a region, budget follows each campaign's warm-up spend (observable): splitting by starting budgets
    # let over-funded campaigns hoard budget they cannot spend (neutral x spent only ~75% of B; logs/P3_log.md).
    # Ephemeral campaigns have no warm-up spend: they get their starting budget × festive, in live runs only.
    f = obs.daily_facts
    warm_spend = f[f.day < WARMUP_DAYS].groupby("campaign_id").spend_inr.sum() / WARMUP_DAYS
    weight = camps.campaign_id.map(warm_spend).fillna(0.0).astype(float)
    for i, r in camps.iterrows():
        if r.sku_id in ephemeral:
            live = _live_overlap(obs, r.sku_id)
            weight[i] = float(r.daily_budget_inr) * fest if live else 0.0
    region = camps.city_id.map(REGION)
    budget = np.zeros(len(camps))
    for g, share in shares.items():
        m = (region == g).to_numpy()
        tot = weight[m].sum()
        if tot > 0:
            budget[m] = daily * share * weight[m].to_numpy() / tot
    camps["daily_budget_inr"] = np.round(budget, 2)
    keep = set(dayparts_for(v["daypart"]))
    for dp in DAYPARTS:
        camps[f"on_{dp}"] = dp in keep
    return camps, ck[["campaign_id", "keyword_id", "bid_cpm_inr", "active"]]
