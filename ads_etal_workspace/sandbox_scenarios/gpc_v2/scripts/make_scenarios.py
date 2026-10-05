"""Write the sim v2 scenario files (design/02 §8) from one place, so shared parameters cannot drift.

    PYTHONPATH=. .venv/bin/python scripts/make_scenarios.py

sc1_cannibal  A           shelf (nested logit, competitor items)
sc2_brand_assoc A, B, D   + intent mix, reformulation, stealing; competitor pacing + opportunism on K01
sc3_festive   A, C, D     + festive event, K11/S6 ephemeral with stock, pull-forward; competitor festive budgets
sc4_seasonal  A, C        + K12 seasonal keyword
sc_all        A–D         everything (integration scenario for E1–E3)

Values are illustrative (doc 02 caveats *2–*5); deviations from the doc are logged in logs/P2_log.md.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

SC = Path(__file__).resolve().parents[1] / "gpc" / "scenarios"

COMPETITOR_UNITS = {"bar": 1800, "liquid": 650}       # hidden base for category_share_weekly

INTENT = {
    "mix": {                                          # doc 02 §3.3 (city-average); unlisted queries are all-open
        "K01": {"aurel": 0.85}, "K02": {"aurel": 0.90},
        "K03": {"aurel": 0.10, "velora": 0.25, "nimbus": 0.05},
        "K04": {"aurel": 0.10, "velora": 0.20, "nimbus": 0.10},
        "K05": {"aurel": 0.05, "velora": 0.05, "nimbus": 0.45},
        "K06": {"aurel": 0.05, "velora": 0.10, "nimbus": 0.30},
        "K07": {"aurel": 0.60, "velora": 0.05},
        "K08": {"aurel": 0.20, "nimbus": 0.10},
        "K09": {"velora": 0.85}, "K10": {"nimbus": 0.90},
        "K11": {"aurel": 0.10, "velora": 0.05},
        "K12": {"aurel": 0.10, "nimbus": 0.10},
    },
    "city_tilt": {                                    # doc 02 §3.5: Aurel stronger South, Velora North
        "aurel": {"BLR": 1.2, "HYD": 1.2, "DEL": 0.85},
        "velora": {"DEL": 1.25, "BLR": 0.85, "HYD": 0.9},
    },
    "city_noise_sigma": 0.08,
    # loyal_buy 0.08, sigma_undef 0.20 (doc range 0.18–0.42) and presence 0.4: K01 defence worth ~4× its spend when
    # conquested (first pass, 0.15 / 0.30 / 0.6, gave ~17× and dominated brand IncRev; logs/P2_log.md)
    "loyal_buy": 0.08, "rho_reform": 0.4, "reform_conv_mult": 2.0,
    "sigma_def": 0.03, "sigma_undef": 0.20, "steal_conv": 0.3,
    "defend": {"velora": {"K09": 0.9, "default": 0.3}, "nimbus": {"K10": 0.9, "default": 0.3}},
    "brand_query": "K01",
    "reformulation_from": ["K03", "K04", "K07", "K08"],
}

AGENTS = {
    "velora": {"keywords": {"K03": 0.35, "K04": 0.30, "K07": 0.25, "K09": 0.60, "K05": 0.15, "K06": 0.15,
                            "K11": 0.30, "K12": 0.20}},
    "nimbus": {"keywords": {"K05": 0.40, "K06": 0.40, "K10": 0.60, "K03": 0.20, "K04": 0.25, "K08": 0.30,
                            "K11": 0.20, "K12": 0.30}},
}
OPPORTUNISM = {"keyword": "K01", "threshold": 0.5, "days": 3, "bid_up": 0.25, "presence": 0.4}
CONQUEST_BASE = {"K01": 0.10, "K02": 0.05, "K07": 0.25}

FESTIVE = {
    "id": "FEST", "peak_day": 56, "ramp_days": 14, "tail_days": 3,
    "demand": {"K11": 6.0, "K03": 1.15, "K04": 1.10, "K07": 1.20, "K01": 1.10},
    "evening_intent_lift": 1.25, "competitor_budget_mult": 2.5,
    # doc: days_after 14; 10 keeps the whole dip (days 60–69) inside the 70-day horizon the scorer sees
    "pull_forward": {"keywords": ["K03", "K04", "K07"], "rho": 0.5, "days_after": 10},
}
K11 = {"id": "K11", "keyword": "bath gift set", "type": "generic", "searches_30d": 90_000, "rank1_cpm_inr": 380,
       "intent": 1.4, "incrementality": 0.7, "live_from": 42, "live_to": 59}
S6 = {"id": "S6", "name": "Aurel Festive Gift Pack", "sub_category": "Soap", "pack": "gift pack", "mrp": 649,
      "asp": 549, "organic_units_per_day": 140, "appeal": 1.15, "start_budget": 1600,
      # doc: 2400/1800/1600/900/600; scaled ×0.65 so stock binds near what the starting bids sell (logs/P2_log.md)
      "stock_by_city": {"DEL": 1560, "MUM": 1170, "BLR": 1040, "HYD": 585, "PUN": 390},
      "live_from": 42, "live_to": 59, "salvage_frac": 0.4}
K12 = {"id": "K12", "keyword": "antibacterial soap", "type": "generic", "searches_30d": 150_000, "rank1_cpm_inr": 340,
       "intent": 1.0, "incrementality": 0.6}
SEASONAL = {"keywords": ["K12"], "shape": "cos", "period_days": 365, "peak_day": 40, "amp": 0.30}
REL_FESTIVE = {"S6": [["K11", 1.0, 2], ["K01", 0.6, 9], ["K03", 0.4, 14]],
               "S1": [["K11", 0.5, None]], "S3": [["K11", 0.5, None]]}
REL_SEASONAL = {"S3": [["K12", 0.8, 3]], "S1": [["K12", 0.5, 7]], "S2": [["K12", 0.4, None]]}
SHELF_FESTIVE = {"V1": {"K11": [0.6, 1]}, "N1": {"K11": [0.5, 3]}}
SHELF_SEASONAL = {"V1": {"K12": [0.7, 2]}, "N1": {"K12": [0.8, 1]}}


def _merge_rel(*rels):
    out = {}
    for r in rels:
        for sku, lst in r.items():
            out.setdefault(sku, []).extend(lst)
    return out


def _shelf_add(sc: dict, extra: dict) -> None:
    for c, kws in extra.items():
        sc["shelf"]["competitors"][c]["keywords"].update(kws)


def main() -> None:
    sc1 = json.loads((SC / "sc1_cannibal.json").read_text())
    sc1["shelf"]["competitor_units_per_day"] = COMPETITOR_UNITS
    (SC / "sc1_cannibal.json").write_text(json.dumps(sc1, indent=2) + "\n")

    def derive(name, note, intent=False, festive=False, seasonal=False, opportunism=False, competitors=False):
        sc = copy.deepcopy(sc1)
        sc["name"], sc["note"] = name, note + " Hidden; policies must not read it."
        cal = {}
        rels = []
        if festive:
            cal.update({"events": [FESTIVE], "ephemeral_keywords": [K11], "ephemeral_skus": [S6]})
            rels.append(REL_FESTIVE)
            _shelf_add(sc, SHELF_FESTIVE)
            sc["keywords"]["K11"] = {"intent": K11["intent"], "incrementality": K11["incrementality"]}
        if seasonal:
            cal.update({"seasonal": [SEASONAL], "extra_keywords": [K12]})
            rels.append(REL_SEASONAL)
            _shelf_add(sc, SHELF_SEASONAL)
        if cal:
            cal["extra_relevance"] = _merge_rel(*rels)
            sc["calendar"] = cal
        if intent:
            sc["intent"] = INTENT
            sc["keywords"]["K07"]["intent"] = 2.0        # owned by Aurel: brand-like direct ROAS (doc 02 §3.3 trap)
            sc["keywords"]["K05"]["intent"] = 0.8        # owned by Nimbus: weak conversion for Aurel
        if competitors:
            sc["competitors"] = {"agents": AGENTS, "spend_elasticity": 2.3, "eta": 0.5}
            if opportunism:
                sc["competitors"]["opportunism"] = OPPORTUNISM
                sc["competitors"]["conquest_base"] = CONQUEST_BASE
        (SC / f"{name}.json").write_text(json.dumps(sc, indent=2) + "\n")

    derive("sc2_brand_assoc", "Sim v2 scenario A+B+D(opportunism): brand-owned queries, stealing, reformulation.",
           intent=True, opportunism=True, competitors=True)
    derive("sc3_festive", "Sim v2 scenario A+C+D: festive event, K11/S6 cold start with stock, pull-forward, CPM inflation.",
           festive=True, competitors=True)
    derive("sc4_seasonal", "Sim v2 scenario A+C(seasonal): K12's season masquerades as ad lift.", seasonal=True)
    derive("sc_all", "Sim v2 integration scenario A–D (E1–E3).",
           intent=True, festive=True, seasonal=True, opportunism=True, competitors=True)
    print("wrote", sorted(p.name for p in SC.glob("sc*.json")))


if __name__ == "__main__":
    main()
