"""Sim v2 P2 gates (design/02 §10 steps 2–4, 6–7) and the §8 traps as regression tests."""
import json
import time

import pandas as pd
import pytest

from gpc import score_v2
from gpc.calendar import Calendar
from gpc.competitors import Competitors
from gpc.holdout import readout
from gpc.market import Market
from gpc.policy import NoOpPolicy, Policy
from gpc.runner import simulate
from gpc.world import SCENARIO_DIR, WARMUP_DAYS, build_world
from scripts.p2_readout import readout as p2_readout

SCENARIOS = ["sc1_cannibal", "sc2_brand_assoc", "sc3_festive", "sc4_seasonal", "sc_all"]


def _spec(name):
    return json.loads((SCENARIO_DIR / f"{name}.json").read_text())


@pytest.fixture(scope="module")
def ro():
    """Mechanism readout (seed 11: an S6 stock-out happens there) for the scenarios that carry each trap."""
    return {s: p2_readout((s, 11)) for s in ("sc2_brand_assoc", "sc3_festive")}


# ── Module C: calendar ─────────────────────────────────────────────────────────
def test_pull_forward_conserves_units():
    cal = Calendar(_spec("sc3_festive")["calendar"])
    ev = cal.events[0]
    lo, hi = cal.window(ev)
    pf = ev["pull_forward"]
    for k in pf["keywords"]:
        excess = sum(cal.search_mult(k, t) - 1 for t in range(lo, hi + 1))
        dip = sum(1 - cal.search_mult(k, t) for t in range(hi + 1, hi + 1 + pf["days_after"]))
        assert excess > 0 and dip == pytest.approx(pf["rho"] * excess, rel=1e-12)
        assert cal.search_mult(k, hi + 1 + pf["days_after"]) == 1.0          # dip ends on time
        assert hi + pf["days_after"] < 70                                   # the scorer sees the whole dip


def test_festive_curve_and_ephemeral_window():
    cal = Calendar(_spec("sc3_festive")["calendar"])
    ev = cal.events[0]
    assert cal.search_mult("K03", ev["peak_day"]) == pytest.approx(ev["demand"]["K03"])
    assert cal.search_mult("K11", 41) == 0.0 and cal.search_mult("K11", 60) == 0.0 and cal.search_mult("K11", 50) > 1
    assert cal.evening_lift(50) == 1.25 and cal.evening_lift(30) == 1.0
    assert [cal.phase(d) for d in (30, 45, 56, 58, 62)] == ["normal", "ramp", "peak", "tail", "post"]


def test_seasonal_peaks_on_its_day():
    cal = Calendar(_spec("sc4_seasonal")["calendar"])
    s = cal.seasonal[0]
    vals = {t: cal.search_mult("K12", t) for t in range(70)}
    assert max(vals, key=vals.get) == s["peak_day"] and vals[s["peak_day"]] == pytest.approx(1 + s["amp"])


# ── Module C: stock ────────────────────────────────────────────────────────────
def test_stock_never_negative_and_osa_zero_after_stockout(ro):
    r = ro["sc3_festive"]
    assert r["stock_min"] >= 0
    assert r["stockout_cities"] >= 1 and r["s6_osa_after_stockout_max"] == 0.0


def test_gift_pack_does_not_exist_outside_its_window():
    w = build_world(7, "sc3_festive")
    t = score_v2.run_schedule(w, n_runs=6)
    s6 = t["sku_city_daily"].query("sku_id == 'S6'")
    assert (s6[(s6.day < 42) | (s6.day > 59)].total_units == 0).all()
    f = t["daily_facts"]
    assert not len(f[(f.keyword_id == "K11") & ((f.day < 42) | (f.day > 59))])


# ── Module D: competitors ──────────────────────────────────────────────────────
def test_festive_cpm_inflation_in_range_and_recovers(ro):
    assert 1.3 <= ro["sc3_festive"]["festive_cpm_ratio_K03"] <= 1.5
    sc = _spec("sc3_festive")
    comp = Competitors(sc["competitors"], Calendar(sc["calendar"]), ["DEL"])
    pm = {}
    for d in range(70):
        pm[d] = comp.price_mult("K03", "DEL")
        comp.end_of_day(d, {})
    assert pm[30] == pytest.approx(1.0) and pm[69] < 1.05 * pm[30]


def test_legacy_price_shock_still_applies():
    m = Market(build_world(7, "sc3_festive"))
    assert m._shock("price", 50, city_id="MUM", keyword_id="K05") == 1.35


def test_pausing_the_brand_query_invites_conquest_and_costs_more_than_it_saves(ro):
    r = ro["sc2_brand_assoc"]
    assert r["probe_pauseK01_conquest_cities_end"] == 5 and r["probe_pauseK01_first_conquest_day"] <= WARMUP_DAYS + 4
    assert r["probe_pauseK01_offtake_lost"] > 2 * r["probe_pauseK01_spend_saved"]


def test_no_conquest_while_aurel_defends():
    t = score_v2.run_schedule(build_world(7, "sc2_brand_assoc"))
    c = t["truth_competitors"]
    assert c[c.agent.str.startswith("conquest_")].bid_level.sum() == 0


# ── Module B: intent ───────────────────────────────────────────────────────────
def test_intent_mix_is_a_distribution_with_city_tilt():
    mix = build_world(7, "sc2_brand_assoc").truth["intent_mix"]
    for p in mix.values():
        assert abs(sum(p.values()) - 1) < 1e-12 and min(p.values()) >= 0
    assert mix[("K07", "BLR")]["aurel"] > mix[("K07", "DEL")]["aurel"]
    assert mix[("K03", "DEL")]["velora"] > mix[("K03", "BLR")]["velora"]


def test_label_trap_K07_behaves_like_a_brand_keyword(ro):
    r = ro["sc2_brand_assoc"]
    assert r["iota_brand_K07"] < 0.5 * r["iota_brand_K03"]                # brand-like incrementality
    assert r["droas_K07"] > 2 * r["warm_droas_generic"]                   # and brand-like direct ROAS
    assert r["iota_brand_K05"] > r["iota_brand_K03"]                      # Nimbus-owned body wash: challenger


def test_reformulation_attribution_illusion(ro):
    r = ro["sc2_brand_assoc"]
    assert r["probe_pauseK03_K01_impr_change"] > 0.02
    assert r["probe_pauseK03_K01_attr_rev_change"] > 0                    # the brand query gets more credit …
    assert r["probe_pauseK03_brand_offtake_change"] < 0                   # … while the brand sells less


def test_decomposition_still_partitions_orders_with_intent():
    w = build_world(7, "sc2_brand_assoc")
    res = simulate(w, NoOpPolicy(), n_runs=1)
    d = res.truth_tables["truth_decomp"]
    assert (abs(d[["self", "sibling", "competitor", "expansion"]].sum(axis=1) - d.ad_orders) < 1e-9).all()
    assert d.ad_orders.sum() == res.daily_facts.ad_orders.sum()


# ── holdout lever ──────────────────────────────────────────────────────────────
class _HoldOne(Policy):
    name = "hold_one"

    def recommend(self, obs):
        self.seen = getattr(self, "seen", {})
        self.seen[obs.run] = obs.extra
        if obs.run == 1:
            return pd.DataFrame([{"campaign_id": "C-S1-DEL", "keyword_id": "K03", "action_type": "request_holdout",
                                  "new_value": None, "reason": "lift test"}])
        return pd.DataFrame(columns=["campaign_id", "keyword_id", "action_type", "new_value", "reason"])


def test_holdout_pauses_one_run_then_reports():
    w = build_world(7, "sc1_cannibal")
    pol = _HoldOne()
    res = simulate(w, pol, n_runs=3)
    f = res.daily_facts
    cell = f[(f.campaign_id == "C-S1-DEL") & (f.keyword_id == "K03")]
    assert not len(cell[(cell.day >= 28) & (cell.day < 35)]) and len(cell[cell.day >= 35])
    lr = pol.seen[2]["lift_readout"]
    assert len(lr) == 1 and lr.ci_lo.iloc[0] < lr.est_inc_rev_per_day.iloc[0] < lr.ci_hi.iloc[0]
    assert "lift_readout" not in pol.seen[1]


def test_holdout_ci_covers_truth_at_least_90pct_over_50_seeds():
    """The readout's noise depends only on the world seed, so a stand-in carrying just `seed` exercises it exactly."""
    from types import SimpleNamespace
    hits = 0
    for seed in range(50):
        truth = 1000.0 + 50 * seed
        r = readout(SimpleNamespace(seed=seed), 1, "C-S1-DEL", "K03", truth)
        hits += r["ci_lo"] <= truth <= r["ci_hi"]
    assert hits / 50 >= 0.90


# ── separation, determinism, speed, calibration ────────────────────────────────
def test_observation_extra_holds_only_public_tables():
    w = build_world(7, "sc_all")
    pol = _HoldOne()
    simulate(w, pol, n_runs=2)
    for extra in pol.seen.values():
        assert not any(k.startswith("truth") for k in extra)
    cs = pol.seen[1]["category_share_weekly"]
    assert 7 * cs.week.max() + 6 + 7 < 28 and cs.own_share.between(0, 1).all()        # 7-day publication lag
    assert 7 * (cs.week.max() + 1) + 6 + 7 >= 28                                       # … and no later than that


def test_counterfactual_deterministic_with_stateful_modules():
    a = score_v2.run_schedule(build_world(23, "sc_all"), lambda c, k: (c, k.assign(active=False)), n_runs=6)
    b = score_v2.run_schedule(build_world(23, "sc_all"), lambda c, k: (c, k.assign(active=False)), n_runs=6)
    for k in a:
        pd.testing.assert_frame_equal(a[k], b[k])


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_scenario_runs_under_30s_and_stays_calibrated(scenario):
    t0 = time.time()
    r = p2_readout((scenario, 7))
    assert time.time() - t0 < 30 * 3                       # readout = 2–4 worlds; doc gate is < 30 s per world
    assert 2.5 <= r["warm_droas_generic"] <= 7.0 and 0.8 <= r["warm_droas_competition"] <= 1.9
    assert 13 <= r["warm_droas_brand"] <= 19
    assert 0.17 <= r["warm_ad_share_units"] <= 0.23 and 0.25 <= r["warm_runout_share"] <= 0.36


def test_score_includes_salvage_for_ephemeral_stock():
    """Regression (found in P3): score() adds S6 salvage into the per-SKU increments (int dtype broke it)."""
    w = build_world(7, "sc3_festive")
    res = simulate(w, NoOpPolicy())
    s = score_v2.score(res, w)
    sal = s["salvage_inr"]
    assert sal["policy"]["S6"] >= 0 and sal["ads_off"]["S6"] >= sal["policy"]["S6"]   # ads sell more of the stock
    assert sum(s["inc_rev_by_sku"].values()) == pytest.approx(s["inc_rev_inr"])
