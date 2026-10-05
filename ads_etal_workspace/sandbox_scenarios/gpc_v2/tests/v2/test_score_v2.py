"""Sim v2 Module F gates (design/02 §10 step 5): counterfactual scorer, decomposition, CRN, calibration."""
import pandas as pd
import pytest

from gpc import score_v2
from gpc.policy import NoOpPolicy
from gpc.runner import simulate
from gpc.world import build_world
from scripts.calib_v2 import readout


@pytest.fixture(scope="module")
def sc1():
    w = build_world(7, "sc1_cannibal")
    res = simulate(w, NoOpPolicy())
    return w, res, score_v2.score(res, w)


def test_counterfactual_is_deterministic_per_seed():
    w = build_world(11, "sc1_cannibal")
    a = score_v2.ads_off(w, n_runs=1)
    score_v2._CF_CACHE.clear()
    b = score_v2.ads_off(build_world(11, "sc1_cannibal"), n_runs=1)
    pd.testing.assert_frame_equal(a, b)


def test_counterfactual_has_no_ads_after_warmup(sc1):
    w, _, _ = sc1
    cf = score_v2.ads_off(w)
    assert (cf[cf.day >= 28].ad_units == 0).all() and (cf[cf.day < 28].ad_units > 0).any()


def test_ads_off_policy_scores_zero(sc1):
    """A run that is the counterfactual itself has zero incremental revenue."""
    w, res, _ = sc1
    fake = type(res)("ads_off", res.daily_facts.iloc[0:0], res.campaign_daily, score_v2.ads_off(w), res.runs, res.warmup_droas)
    assert score_v2.score(fake, w)["inc_rev_inr"] == 0


def test_decomposition_sums_to_attributed_orders(sc1):
    _, res, s = sc1
    dec = res.truth_tables["truth_decomp"]
    tot = dec[["self", "sibling", "competitor", "expansion"]].sum(axis=1)
    assert (abs(tot - dec.ad_orders) < 1e-9).all()
    f = res.daily_facts
    assert dec.ad_orders.sum() == f.ad_orders.sum()          # every ad order is decomposed


def test_realised_increv_matches_expected_brand_incremental_orders(sc1):
    """IncRev from the counterfactual ≈ Σ (competitor + expansion) × ASP from the expected split."""
    w, res, s = sc1
    asp = w.public["products"].set_index("sku_id").asp_inr
    dec = res.truth_tables["truth_decomp"]
    dec = dec[dec.day >= 28]
    expected = float(((dec.competitor + dec.expansion) * dec.sku_id.map(asp)).sum())
    assert abs(s["inc_rev_inr"] / expected - 1) < 0.03


def test_sibling_gap_is_visible(sc1):
    """The trap: SKU-level incrementality exceeds brand-level by the sibling share."""
    _, _, s = sc1
    d = s["decomposition"]
    iota_sku = 1 - d["self"] / d["ad_orders"]
    iota_brand = (d["competitor"] + d["expansion"]) / d["ad_orders"]
    assert iota_sku - iota_brand == pytest.approx(d["sibling"] / d["ad_orders"]) and d["sibling"] / d["ad_orders"] > 0.1


@pytest.mark.parametrize("seed", [7, 11])
def test_sc1_calibration(seed):
    r = readout(seed, "sc1_cannibal")
    assert 2.5 <= r["droas_generic"] <= 7.0 and 0.8 <= r["droas_competition"] <= 1.9 and 13 <= r["droas_brand"] <= 19
    assert 0.17 <= r["ad_share_units"] <= 0.23 and 0.25 <= r["runout_share"] <= 0.36
    assert 0.05 <= r["iota_brand_brand"] <= 0.25 and 0.4 <= r["iota_brand_generic"] <= 0.7 and r["iota_brand_competition"] >= 0.8
