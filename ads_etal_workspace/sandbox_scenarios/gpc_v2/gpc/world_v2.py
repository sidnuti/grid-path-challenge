"""Sim v2 world extensions: new keywords and SKUs (calendar), the intent mix, competitor agents, public v2 tables.

Called from `world.build_world` after every legacy draw, with its own RNG stream, so a scenario without
v2 blocks builds exactly the legacy world (goldens) and the legacy entities of a v2 world keep their values.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .world import DAYPARTS, SLOT_VIEW_REL, SLOTS, World, _BID_MULT

V2_WORLD_STREAM = 3001


def extend(world: World, spec: dict) -> None:
    rng = np.random.default_rng(np.random.SeedSequence([world.seed, V2_WORLD_STREAM]))
    cal = spec.get("calendar")
    if cal:
        world.truth["calendar"] = dict(cal, _ephemeral_ids=[e["id"] for e in cal.get("ephemeral_keywords", [])
                                                            + cal.get("ephemeral_skus", [])])
        _add_entities(world, cal, rng)
        world.public["calendar_public"] = _calendar_public(cal)
        world.truth["calendar"] = dict(cal, _ephemeral_ids=[e["id"] for e in cal.get("ephemeral_keywords", [])
                                                            + cal.get("ephemeral_skus", [])])
        from .calendar import Calendar
        world.truth["_calendar_obj"] = Calendar(cal)
    if spec.get("shelf"):
        sh = spec["shelf"]
        world.truth["shelf_spec"] = sh
        world.public["shelf_ranks"] = pd.DataFrame(
            [{"keyword_id": k, "item_id": c, "brand": v["brand"], "organic_rank": r}
             for c, v in sh["competitors"].items() for k, (_, r) in v["keywords"].items()]
            + [{"keyword_id": r.keyword_id, "item_id": r.sku_id, "brand": "Aurel", "organic_rank": r.organic_rank}
               for r in world.public["keyword_sku"].itertuples()])
    if spec.get("intent"):
        from .intent import build_intent
        world.truth["intent_mix"] = build_intent(spec["intent"], list(world.public["keywords"].keyword_id),
                                                 list(world.public["cities"].city_id), world.seed)
        world.truth["intent"] = spec["intent"]
    if spec.get("competitors"):
        world.truth["competitors"] = spec["competitors"]


def _add_entities(world: World, cal: dict, rng: np.random.Generator) -> None:
    p, t = world.public, world.truth
    cities = p["cities"]
    new_kw = cal.get("ephemeral_keywords", []) + cal.get("extra_keywords", [])
    new_sku = cal.get("ephemeral_skus", [])
    if new_kw:
        p["keywords"] = pd.concat([p["keywords"], pd.DataFrame(
            [{"keyword_id": k["id"], "keyword": k["keyword"], "keyword_type": k["type"],
              "searches_30d": k["searches_30d"], "rank1_cpm_inr": k["rank1_cpm_inr"]} for k in new_kw])],
            ignore_index=True)
    for k in new_kw:                                     # hidden response parameters, same priors as world._truth
        t["keywords"][k["id"]] = {
            "intent": k["intent"] * float(np.exp(rng.normal(0, 0.08))),
            "incrementality": float(np.clip(k["incrementality"] + rng.normal(0, 0.04), 0.05, 0.95)),
            "view_dev": {s: float(np.exp(rng.normal(0, 0.10))) if s != 1 else 1.0 for s in SLOTS},
            "conv_dev": {s: float(np.exp(rng.normal(0, 0.10))) for s in SLOTS},
            "price_dev": {s: float(np.exp(rng.normal(0, 0.05))) if s != 1 else 1.0 for s in SLOTS},
        }
        for c in cities.city_id:
            t["city_kw_affinity"][(c, k["id"])] = float(np.exp(rng.normal(0, 0.12)))
    if new_sku:
        p["products"] = pd.concat([p["products"], pd.DataFrame(
            [{"sku_id": s["id"], "sku_name": s["name"], "sub_category": s["sub_category"], "pack": s["pack"],
              "mrp_inr": s["mrp"], "asp_inr": s["asp"], "organic_units_per_day": s["organic_units_per_day"],
              "launch_age_days": 0} for s in new_sku])], ignore_index=True)
        p["sku_city"] = pd.concat([p["sku_city"], pd.DataFrame(
            [{"sku_id": s["id"], "city_id": c, "base_osa": round(float(np.clip(rng.normal(0.95, 0.02), 0.9, 0.99)), 3)}
             for s in new_sku for c in cities.city_id])], ignore_index=True)
        for s in new_sku:
            t["appeal"][s["id"]] = float(s.get("appeal", 1.0))
    rel = cal.get("extra_relevance", {})
    if rel:
        p["keyword_sku"] = pd.concat([p["keyword_sku"], pd.DataFrame(
            [{"sku_id": sku, "keyword_id": k, "relevance": r, "organic_rank": np.nan if o is None else o}
             for sku, lst in rel.items() for k, r, o in lst])], ignore_index=True)
        for sku, lst in rel.items():                     # legacy step-6 damping is unused when the shelf is on
            for k, _, _ in lst:
                t["organic_damp"][(sku, k)] = 1.0
    _add_campaigns(world, new_sku, rel, rng)


def _add_campaigns(world: World, new_sku: list[dict], rel: dict, rng: np.random.Generator) -> None:
    """Campaign rows for new SKUs (one per city) and campaign_keywords rows for every new (SKU, keyword) cell."""
    p = world.public
    kw = p["keywords"].set_index("keyword_id")
    cities = p["cities"].set_index("city_id")
    camp_rows, ck_rows, plan_rows = [], [], []
    for s in new_sku:
        for c, crow in cities.iterrows():
            budget = max(400.0, round(s.get("start_budget", 1500) * crow.demand_share * 5 / 50) * 50)
            camp_rows.append({"campaign_id": f"C-{s['id']}-{c}", "campaign_name": f"AUR_{s['id']}_{c}_PB",
                              "sku_id": s["id"], "city_id": c, "ad_type": "Product Booster",
                              "daily_budget_inr": float(budget), **{f"on_{dp}": True for dp in DAYPARTS}})
    if camp_rows:
        p["campaigns"] = pd.concat([p["campaigns"], pd.DataFrame(camp_rows)], ignore_index=True)
    goal_base = {"brand": 9.0, "generic": 3.2, "competition": 1.6}
    for sku, lst in rel.items():
        for k, r, _ in lst:
            for c, crow in cities.iterrows():
                cid = f"C-{sku}-{c}"
                rank1 = kw.loc[k, "rank1_cpm_inr"] * crow.cpm_index
                bid = float(np.clip(round(rank1 * _BID_MULT[kw.loc[k, "keyword_type"]]
                                          * float(np.exp(rng.normal(0, 0.10))) / 5) * 5, 200, 10_000))
                ck_rows.append({"campaign_id": cid, "keyword_id": k, "bid_cpm_inr": bid, "active": True})
                goal = goal_base[kw.loc[k, "keyword_type"]] * float(np.exp(rng.normal(0, 0.25)))
                plan_rows.append({"sku_id": sku, "city_id": c, "keyword_id": k, "plan_budget_inr_day": 0,
                                  "goal_droas": round(goal, 2), "marginal_floor_droas": round(max(1.0, goal * 0.45), 2),
                                  "evidence_tier": "low"})
    # existing campaigns that gain an always-on keyword get budget for it, sized like world._campaigns does
    # (an ephemeral keyword is not live in warm-up, so it gets none: funding it is the policy's decision)
    ephemeral = set(world.truth.get("calendar", {}).get("_ephemeral_ids", []))
    camp = p["campaigns"].set_index("campaign_id")
    for r in ck_rows:
        sku, k = r["campaign_id"].split("-")[1], r["keyword_id"]
        if k in ephemeral or sku in {s["id"] for s in new_sku}:
            continue
        c = cities.loc[r["campaign_id"].split("-")[2]]
        rank1 = kw.loc[k, "rank1_cpm_inr"] * c.cpm_index
        relv = next(x[1] for x in rel[sku] if x[0] == k)
        searches = kw.loc[k, "searches_30d"] / 30 * c.demand_share * relv
        slot_guess = 1 if r["bid_cpm_inr"] >= rank1 else (5 if r["bid_cpm_inr"] >= rank1 * 0.94 else 9)
        camp.loc[r["campaign_id"], "daily_budget_inr"] += round(
            searches * SLOT_VIEW_REL[slot_guess] * rank1 * 0.9 / 1000 / 50) * 50
    p["campaigns"] = camp.reset_index()
    if ck_rows:
        p["campaign_keywords"] = pd.concat([p["campaign_keywords"], pd.DataFrame(ck_rows)], ignore_index=True)
        p["plan"] = pd.concat([p["plan"], pd.DataFrame(plan_rows)], ignore_index=True)


def _calendar_public(cal: dict) -> pd.DataFrame:
    """What a brand knows about its own calendar: events, live windows, gift-pack stock (doc 02 §7.2)."""
    rows = []
    for ev in cal.get("events", []):
        rows.append({"kind": "event", "id": ev["id"], "from_day": ev["peak_day"] - ev["ramp_days"],
                     "to_day": ev["peak_day"] + ev.get("tail_days", 0), "peak_day": ev["peak_day"], "detail": ""})
    for k in cal.get("ephemeral_keywords", []):
        rows.append({"kind": "ephemeral_keyword", "id": k["id"], "from_day": k["live_from"], "to_day": k["live_to"],
                     "peak_day": None, "detail": k["keyword"]})
    for s in cal.get("ephemeral_skus", []):
        rows.append({"kind": "ephemeral_sku", "id": s["id"], "from_day": s["live_from"], "to_day": s["live_to"],
                     "peak_day": None, "detail": json.dumps({"stock_by_city": s["stock_by_city"],
                                                             "salvage_frac": s["salvage_frac"]})})
    return pd.DataFrame(rows)
