"""The synthetic world: base data for cities, products, keywords and campaigns.

Everything here is fictional (brand "Aurel", competitors "Velora" and "Nimbus"), but the
magnitudes are calibrated to aggregated Blinkit production data — see CALIBRATION.md.

Two kinds of data come out of `build_world`:

* PUBLIC tables (`World.public`) — what an operator or a policy can see: attributes, search
  volumes, list prices, the starting campaign set-up, the media plan, industry priors.
* HIDDEN truth (`World.truth`) — the market's real response parameters (keyword intent,
  incrementality, per-keyword curve deviations, scheduled shocks). Only `market.py` reads it.
  A policy never receives it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

# ── ad slots and dayparts ──────────────────────────────────────────────────────
# Blinkit sponsored slots cluster at positions 1 / 5 / 9 / 13 (≈91% of industry-curve rows).
SLOTS: tuple[int, ...] = (1, 5, 9, 13)
# Industry rank curve, medians across keywords, paired per keyword against slot 1.
SLOT_VIEW_REL = {1: 1.00, 5: 0.41, 9: 0.17, 13: 0.08}       # impressions per search vs slot 1
SLOT_PRICE_REL = {1: 1.00, 5: 0.94, 9: 0.86, 13: 0.76}      # clearing CPM vs slot 1
SLOT_CONV = {1: 0.0085, 5: 0.0060, 9: 0.0039, 13: 0.0029}   # orders per impression (median keyword)

DAYPARTS: tuple[str, ...] = ("night", "morning", "afternoon", "evening")
DAYPART_HOURS = {"night": "00–06", "morning": "06–12", "afternoon": "12–18", "evening": "18–24"}
DAYPART_SHARE = (0.11, 0.26, 0.33, 0.30)                    # share of daily searches
DAYPART_PRICE = (0.98, 1.00, 1.01, 0.99)                    # rank-1 bid level by daypart

START_DATE = date(2026, 8, 3)       # a Monday
WARMUP_DAYS = 28
RUN_DAYS = 7
N_RUNS = 6


@dataclass
class World:
    public: dict[str, pd.DataFrame]
    truth: dict = field(default_factory=dict)
    seed: int = 0
    scenario: str = "dev"


# ── base attributes ────────────────────────────────────────────────────────────
def _cities() -> pd.DataFrame:
    rows = [
        # city_id, name, tier, demand_share, cpm_index, dark_stores, daypart tilt
        ("DEL", "Delhi NCR", 1, 0.32, 1.00, 310, (0.11, 0.26, 0.33, 0.30)),
        ("MUM", "Mumbai", 1, 0.24, 1.12, 220, (0.12, 0.25, 0.31, 0.32)),
        ("BLR", "Bengaluru", 1, 0.22, 1.06, 240, (0.10, 0.24, 0.31, 0.35)),
        ("HYD", "Hyderabad", 1, 0.13, 0.92, 130, (0.11, 0.27, 0.33, 0.29)),
        ("PUN", "Pune", 2, 0.09, 0.88, 95, (0.11, 0.27, 0.34, 0.28)),
    ]
    out = []
    for cid, name, tier, share, cpm_idx, stores, tilt in rows:
        out.append({
            "city_id": cid, "city_name": name, "tier": tier, "demand_share": share,
            "cpm_index": cpm_idx, "dark_stores": stores,
            **{f"share_{dp}": s for dp, s in zip(DAYPARTS, tilt)},
        })
    return pd.DataFrame(out)


def _products() -> pd.DataFrame:
    rows = [
        # sku_id, name, sub_category, pack, mrp, asp, base organic units/day (5 cities), launch age
        ("S1", "Aurel Sandal Glow Soap", "Soap", "4 × 100 g", 200, 172, 900, 900),
        ("S2", "Aurel Charcoal Body Wash", "Body Wash", "250 ml", 325, 279, 260, 540),
        ("S3", "Aurel Aloe Fresh Soap", "Soap", "3 × 125 g", 165, 149, 640, 1200),
        ("S4", "Aurel Lime Shower Gel", "Shower Gel", "500 ml", 499, 424, 140, 300),
        ("S5", "Aurel Kids Bubble Bar", "Kids Soap", "4 × 75 g", 140, 126, 70, 45),
    ]
    return pd.DataFrame(rows, columns=[
        "sku_id", "sku_name", "sub_category", "pack", "mrp_inr", "asp_inr",
        "organic_units_per_day", "launch_age_days"])


# keyword, type, 30-day searches (5 cities), rank-1 CPM ₹ (median city), HIDDEN intent, HIDDEN incrementality
_KEYWORDS = [
    ("K01", "aurel", "brand", 180_000, 210, 2.4, 0.15),
    ("K02", "aurel soap", "brand", 62_000, 230, 2.6, 0.18),
    ("K03", "soap", "generic", 920_000, 360, 0.9, 0.55),
    ("K04", "bathing soap", "generic", 240_000, 330, 1.0, 0.55),
    ("K05", "body wash", "generic", 310_000, 390, 1.0, 0.60),
    ("K06", "shower gel", "generic", 140_000, 420, 1.05, 0.60),
    ("K07", "sandal soap", "generic", 95_000, 300, 1.15, 0.50),
    ("K08", "kids soap", "generic", 45_000, 280, 1.2, 0.70),
    ("K09", "velora", "competition", 260_000, 470, 0.5, 0.85),
    ("K10", "nimbus body wash", "competition", 110_000, 440, 0.45, 0.85),
]

# sku → [(keyword_id, relevance 0–1, organic rank of the SKU on that keyword or None)]
_RELEVANCE = {
    "S1": [("K01", 1.0, 2), ("K02", 1.0, 1), ("K03", 0.8, 6), ("K04", 0.8, 5), ("K07", 1.0, 3), ("K09", 0.6, None)],
    "S2": [("K01", 0.9, 4), ("K05", 1.0, 4), ("K06", 0.7, 9), ("K10", 0.8, None)],
    "S3": [("K01", 0.9, 3), ("K02", 0.9, 2), ("K03", 0.85, 4), ("K04", 0.85, 3), ("K09", 0.6, None)],
    "S4": [("K01", 0.8, 6), ("K05", 0.8, 7), ("K06", 1.0, 5), ("K10", 0.7, None)],
    "S5": [("K01", 0.7, 8), ("K03", 0.5, 20), ("K08", 1.0, 6)],
}

# Starting bid level per keyword type, as a multiple of that city's rank-1 CPM. Brand bids sit at
# the top; competitor bids are aggressive (a habit the data should eventually argue against).
_BID_MULT = {"brand": 1.08, "generic": 0.90, "competition": 1.05}


def _keywords() -> pd.DataFrame:
    return pd.DataFrame(
        [(k, kw, t, sv, cpm) for k, kw, t, sv, cpm, _i, _inc in _KEYWORDS],
        columns=["keyword_id", "keyword", "keyword_type", "searches_30d", "rank1_cpm_inr"])


def _keyword_sku() -> pd.DataFrame:
    rows = []
    for sku, lst in _RELEVANCE.items():
        for kid, rel, org in lst:
            rows.append({"sku_id": sku, "keyword_id": kid, "relevance": rel,
                         "organic_rank": org if org is not None else np.nan})
    return pd.DataFrame(rows)


def _sku_city(rng: np.random.Generator, cities: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, p in products.iterrows():
        for _, c in cities.iterrows():
            osa = float(np.clip(rng.normal(0.93, 0.025), 0.85, 0.98))
            if p.sku_id == "S4" and c.city_id == "PUN":
                osa = 0.78                                  # a chronically patchy SKU × city
            rows.append({"sku_id": p.sku_id, "city_id": c.city_id, "base_osa": round(osa, 3)})
    return pd.DataFrame(rows)


def _industry_curve() -> pd.DataFrame:
    return pd.DataFrame([
        {"slot": s, "view_rel": SLOT_VIEW_REL[s], "price_rel": SLOT_PRICE_REL[s], "conv_per_impr": SLOT_CONV[s]}
        for s in SLOTS])


def _dayparts() -> pd.DataFrame:
    return pd.DataFrame([
        {"daypart": dp, "hours": DAYPART_HOURS[dp], "search_share": DAYPART_SHARE[i], "bid_level": DAYPART_PRICE[i]}
        for i, dp in enumerate(DAYPARTS)])


# ── hidden truth ───────────────────────────────────────────────────────────────
def _truth(rng: np.random.Generator, scenario: str, keywords: pd.DataFrame, keyword_sku: pd.DataFrame,
           cities: pd.DataFrame) -> dict:
    kw_truth = {}
    for k, _kw, _t, _sv, _cpm, intent, inc in _KEYWORDS:
        kw_truth[k] = {
            "intent": intent * float(np.exp(rng.normal(0, 0.08))),
            "incrementality": float(np.clip(inc + rng.normal(0, 0.04), 0.05, 0.95)),
            # per-keyword deviation of the rank curve from the industry median
            "view_dev": {s: float(np.exp(rng.normal(0, 0.10))) if s != 1 else 1.0 for s in SLOTS},
            "conv_dev": {s: float(np.exp(rng.normal(0, 0.10))) for s in SLOTS},
            "price_dev": {s: float(np.exp(rng.normal(0, 0.05))) if s != 1 else 1.0 for s in SLOTS},
        }
    appeal = {"S1": 1.0, "S2": 0.95, "S3": 1.0, "S4": 0.9, "S5": 1.1}
    # a SKU that ranks top-3 organically gains little from an ad on that keyword
    organic_damp = {(r.sku_id, r.keyword_id): (0.6 if (not np.isnan(r.organic_rank) and r.organic_rank <= 3) else 1.0)
                    for r in keyword_sku.itertuples()}
    city_kw_affinity = {(c, k): float(np.exp(rng.normal(0, 0.12))) for c in cities.city_id for k in keywords.keyword_id}

    run_start = lambda r: WARMUP_DAYS + (r - 1) * RUN_DAYS  # noqa: E731  (day index of run r's first day)
    if scenario == "dev":
        shocks = [
            # supply: S2 out of stock in most Hyderabad stores for one week
            {"kind": "osa", "sku_id": "S2", "city_id": "HYD", "from_day": run_start(3), "to_day": run_start(4) - 1, "osa": 0.42},
            # competition: a rival starts bidding up body wash / shower gel in Mumbai and keeps going
            {"kind": "price", "city_id": "MUM", "keyword_ids": ["K05", "K06"], "from_day": run_start(4), "mult": 1.35},
            # demand: soap searches rise 15% from the last two runs (seasonal)
            {"kind": "demand", "keyword_ids": ["K03", "K04"], "from_day": run_start(5), "mult": 1.15},
        ]
    else:
        # The eval scenario lives outside this repo (Gobblecube keeps it). Same kinds of shock,
        # different SKUs, cities, keywords and timing — so a policy cannot be tuned to dev's.
        import json
        import os
        path = os.environ.get("GPC_EVAL_SCENARIO")
        if not path:
            raise SystemExit("scenario 'eval' needs GPC_EVAL_SCENARIO=<path to the private scenario file>")
        spec = json.load(open(path))
        shocks = [{**sh, "from_day": run_start(sh.pop("from_run")),
                   **({"to_day": run_start(sh.pop("to_run") + 1) - 1} if "to_run" in sh else {})}
                  for sh in spec["shocks"]]
    return {"keywords": kw_truth, "appeal": appeal, "organic_damp": organic_damp,
            "city_kw_affinity": city_kw_affinity, "shocks": shocks,
            "noise": {"searches_sigma": 0.10, "price_sigma": 0.08, "organic_sigma": 0.06, "weekend_lift": 1.12}}


# ── starting campaigns and the plan ────────────────────────────────────────────
def _campaigns(rng: np.random.Generator, cities, products, keywords, keyword_sku) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One campaign per SKU × city. Returns (campaigns, campaign_keywords)."""
    kw = keywords.set_index("keyword_id")
    camp_rows, ck_rows = [], []
    for _, p in products.iterrows():
        for _, c in cities.iterrows():
            cid = f"C-{p.sku_id}-{c.city_id}"
            exp_spend = 0.0
            for r in keyword_sku[keyword_sku.sku_id == p.sku_id].itertuples():
                k = kw.loc[r.keyword_id]
                rank1 = k.rank1_cpm_inr * c.cpm_index
                bid = rank1 * _BID_MULT[k.keyword_type] * float(np.exp(rng.normal(0, 0.10)))
                bid = float(np.clip(round(bid / 5) * 5, 200, 10_000))
                ck_rows.append({"campaign_id": cid, "keyword_id": r.keyword_id, "bid_cpm_inr": bid, "active": True})
                # rough expected spend at that bid to size a plausible starting budget
                searches = k.searches_30d / 30 * c.demand_share * r.relevance
                slot_guess = 1 if bid >= rank1 else (5 if bid >= rank1 * 0.94 else 9)
                exp_spend += searches * SLOT_VIEW_REL[slot_guess] * rank1 * SLOT_PRICE_REL[slot_guess] / 1000
            # some campaigns start starved (run out early), some over-funded
            factor = float(rng.choice([0.6, 0.8, 1.0, 1.25, 1.6]))
            budget = max(400.0, round(exp_spend * factor / 50) * 50)
            camp_rows.append({
                "campaign_id": cid, "campaign_name": f"AUR_{p.sku_id}_{c.city_id}_PB",
                "sku_id": p.sku_id, "city_id": c.city_id, "ad_type": "Product Booster",
                "daily_budget_inr": budget,
                **{f"on_{dp}": True for dp in DAYPARTS},
            })
    return pd.DataFrame(camp_rows), pd.DataFrame(ck_rows)


def _plan(rng: np.random.Generator, campaigns: pd.DataFrame, campaign_keywords: pd.DataFrame,
          keywords: pd.DataFrame) -> pd.DataFrame:
    """The media plan (stand-in for MMM output): a ₹/day budget, a direct-ROAS goal and a marginal
    floor per cell (SKU × city × keyword). Deliberately approximate, like a real MMM read."""
    kt = keywords.set_index("keyword_id").keyword_type
    goal_base = {"brand": 9.0, "generic": 3.2, "competition": 1.6}
    rows = []
    for r in campaign_keywords.merge(campaigns[["campaign_id", "sku_id", "city_id", "daily_budget_inr"]]).itertuples():
        t = kt[r.keyword_id]
        goal = goal_base[t] * float(np.exp(rng.normal(0, 0.25)))
        rows.append({
            "sku_id": r.sku_id, "city_id": r.city_id, "keyword_id": r.keyword_id,
            "plan_budget_inr_day": round(r.daily_budget_inr / max(1, (campaign_keywords.campaign_id == r.campaign_id).sum())
                                         * float(np.exp(rng.normal(0.15, 0.30))) / 10) * 10,
            "goal_droas": round(goal, 2),
            "marginal_floor_droas": round(max(1.0, goal * 0.45), 2),
            "evidence_tier": rng.choice(["high", "medium", "low"], p=[0.4, 0.4, 0.2]),
        })
    return pd.DataFrame(rows)


def build_world(seed: int = 7, scenario: str = "dev") -> World:
    rng = np.random.default_rng(seed)
    cities, products = _cities(), _products()
    keywords, keyword_sku = _keywords(), _keyword_sku()
    sku_city = _sku_city(rng, cities, products)
    campaigns, campaign_keywords = _campaigns(rng, cities, products, keywords, keyword_sku)
    plan = _plan(rng, campaigns, campaign_keywords, keywords)
    truth = _truth(rng, scenario, keywords, keyword_sku, cities)
    public = {
        "cities": cities, "products": products, "keywords": keywords, "keyword_sku": keyword_sku,
        "sku_city": sku_city, "campaigns": campaigns, "campaign_keywords": campaign_keywords,
        "plan": plan, "industry_rank_curve": _industry_curve(), "dayparts": _dayparts(),
    }
    return World(public=public, truth=truth, seed=seed, scenario=scenario)
