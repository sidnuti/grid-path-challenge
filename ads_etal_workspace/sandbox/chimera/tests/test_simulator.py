"""EcommerceSimulatorV5: formula checks (hand-computed expectations) + reproduction of the repo's own
`results/preprint_results/ecom/environment/*.csv` from `preprint/environment_dynamics_analysis.py`."""
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.components import COST_PER_ITEM, EcommerceSimulatorV5

pytestmark = pytest.mark.offline
UP = Path(__file__).resolve().parents[1] / "upstream"


def sim(**kw):
    kw.setdefault("noise_sigma", 0.0)      # rng.normal(1, 0) == 1 -> deterministic formula checks
    kw.setdefault("seed", 0)
    return EcommerceSimulatorV5(**kw)


def set_state(s, **kw):
    s.state.update(kw)
    s._update_sales_and_profit()
    return s


def expected_demand(trust, price, ad, phase=0, amp=0.2, base=800.0, elast=1.2, k=0.3):
    season = max(0.75, 1.0 + amp * math.sin(2 * math.pi * (phase % 52) / 52.0)) if amp > 0 else 1.0
    return base * trust * (1 + k * math.log1p(ad / 1000.0)) * (price / 100.0) ** (-elast) * season


@pytest.mark.parametrize("price", [50, 80, 100, 125, 150])
def test_price_elasticity_exponent(price):
    s = set_state(sim(), price=price, brand_trust=0.7, weekly_ad_spend=500, season_phase=0)
    assert s.state["sales_volume"] == int(expected_demand(0.7, price, 500))


@pytest.mark.parametrize("ad", [0, 100, 1000, 2500, 5000])
def test_ad_response_is_logarithmic(ad):
    s = set_state(sim(), price=100.0, brand_trust=0.7, weekly_ad_spend=ad, season_phase=0)
    assert s.state["sales_volume"] == int(expected_demand(0.7, 100.0, ad))


def test_ad_response_has_diminishing_returns():
    vols = [set_state(sim(), price=100.0, weekly_ad_spend=a, brand_trust=0.7, season_phase=0).state["sales_volume"]
            for a in (0, 1000, 2000, 3000, 4000, 5000)]
    gains = np.diff(vols)
    assert all(g > 0 for g in gains) and all(gains[i] >= gains[i + 1] - 1 for i in range(len(gains) - 1))


@pytest.mark.parametrize("phase", range(0, 52, 7))
def test_seasonality(phase):
    s = set_state(sim(), price=100.0, brand_trust=0.7, weekly_ad_spend=500, season_phase=phase)
    assert s.state["sales_volume"] == int(expected_demand(0.7, 100.0, 500, phase))


def test_seasonality_floor_is_inactive_at_default_amplitude():
    """Finding: the 0.75 floor never binds with the default amp=0.2 (min factor is 0.8); it only matters for amp > 0.25."""
    s = sim()
    factors = []
    for ph in range(52):
        s.state["season_phase"] = ph
        factors.append(s._seasonality_factor())
    assert min(factors) == pytest.approx(0.8, abs=1e-3) and min(factors) > 0.75


def test_seasonality_floor_binds_for_large_amplitude():
    s = sim(seasonality_amp=0.5)
    s.state["season_phase"] = 39          # sin(2*pi*39/52) = -1
    assert s._seasonality_factor() == 0.75


def test_seasonality_disabled():
    s = sim(seasonality_amp=0.0)
    s.state["season_phase"] = 13
    assert s._seasonality_factor() == 1.0


def test_demand_linear_in_trust():
    a = set_state(sim(), brand_trust=0.4, price=100.0, weekly_ad_spend=500, season_phase=0).state["sales_volume"]
    b = set_state(sim(), brand_trust=0.8, price=100.0, weekly_ad_spend=500, season_phase=0).state["sales_volume"]
    assert abs(b - 2 * a) <= 1


@pytest.mark.parametrize("price,ad,phase", [(100, 500, 0), (60, 4000, 13), (140, 0, 39)])
def test_profit_identity(price, ad, phase):
    s = set_state(sim(), price=price, weekly_ad_spend=ad, season_phase=phase, brand_trust=0.7)
    v = s.state["sales_volume"]
    assert s.state["profit"] == pytest.approx(v * price - (v * COST_PER_ITEM + ad))


def test_noise_is_clipped_to_plus_minus_20_percent():
    s = sim(noise_sigma=5.0, seed=1)          # absurd sigma: the 0.8..1.2 clip must still hold
    base = expected_demand(0.7, 100.0, 500)
    for _ in range(200):
        s._update_sales_and_profit()
        assert 0.8 * base - 1 <= s.state["sales_volume"] <= 1.2 * base + 1


def _trust_after(price_change=0.0, ad=0.0, trust=0.7):
    s = set_state(sim(), brand_trust=trust, price=100.0, weekly_ad_spend=500)
    s.step({"price_change": price_change, "ad_spend": ad})
    return s.state["brand_trust"]


DECAY = 1 - 0.002


def test_trust_rule_price_increase_over_10pct():
    assert _trust_after(0.11) == pytest.approx(0.7 * 0.98 * DECAY)


def test_trust_rule_price_cut_over_5pct():
    assert _trust_after(-0.06) == pytest.approx(0.7 * 1.03 * DECAY)


@pytest.mark.parametrize("pc", [0.10, 0.0, -0.05, 0.05])
def test_trust_rule_boundaries_are_strict(pc):
    assert _trust_after(pc) == pytest.approx(0.7 * DECAY)       # exactly +10% / -5% do not trigger


def test_trust_ad_bonus_and_decay():
    assert _trust_after(0.0, ad=2000.0) == pytest.approx(0.7 * (1 + math.log1p(2.0) * 0.01) * DECAY)


def test_trust_clipped_to_unit_interval():
    assert _trust_after(-0.06, ad=5000.0, trust=1.0) == 1.0
    assert _trust_after(0.2, trust=0.2) == 0.2


def test_step_advances_week_phase_and_clips_price():
    s = set_state(sim(), price=140.0, season_phase=51)
    s.step({"price_change": 0.5, "ad_spend": 99_999})
    assert s.state["price"] == 150.0 and s.state["weekly_ad_spend"] == 5000.0
    assert s.state["season_phase"] == 0 and s.state["week"] == 2


def test_same_seed_same_trajectory():
    def run():
        s = EcommerceSimulatorV5(seed=7)
        return [s.step({"price_change": 0.02, "ad_spend": 800})["profit"] for _ in range(10)]
    assert run() == run()


# ---- reproduction of the repo's environment CSVs --------------------------------------------------------------
@pytest.fixture(scope="module")
def dynamics():
    import importlib
    mod = importlib.import_module("preprint.environment_dynamics_analysis")
    base = {"price": 100.0, "brand_trust": 0.7, "weekly_ad_spend": 500.0, "season_phase": 10}
    s = EcommerceSimulatorV5(seed=42)
    return {
        "price_elasticity": mod.analyze_price_elasticity(s, base),
        "trust_effect": mod.analyze_trust_effect(s, base),
        "ad_spend": mod.analyze_ad_spend_effect(s, base),
        "seasonality": mod.analyze_seasonality(s, base),
    }


@pytest.mark.parametrize("name", ["price_elasticity", "trust_effect", "ad_spend", "seasonality"])
def test_dynamics_csv_reproduces(dynamics, name):
    ref = pd.read_csv(UP / "results" / "preprint_results" / "ecom" / "environment" / f"dynamics_{name}.csv")
    got = dynamics[name]
    assert list(got.columns) == list(ref.columns)
    assert len(got) == len(ref)
    for c in ref.columns:
        np.testing.assert_allclose(got[c].to_numpy(float), ref[c].to_numpy(float), rtol=0, atol=1e-6, err_msg=c)
