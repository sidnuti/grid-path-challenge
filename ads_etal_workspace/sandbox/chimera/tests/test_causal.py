"""CausalEngineV6 (CausalForestDML): data regeneration, effect quality vs a Monte-Carlo ground truth from the simulator,
SHAP additivity, retrain bookkeeping. ~10 s to fit once per module."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import spearmanr

from src.components import CausalEngineV6, EcommerceSimulatorV5

pytestmark = [pytest.mark.offline, pytest.mark.slow]
RESULTS = Path(__file__).resolve().parents[1] / "runs" / "results"


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    return CausalEngineV6(data_path=str(tmp_path_factory.mktemp("c") / "d.pkl"), force_regenerate=True)


def ctx(price, ad, trust, phase):
    return dict(week=1, price=price, weekly_ad_spend=ad, brand_trust=trust, sales_volume=0, profit=0.0, season_phase=phase)


def true_effect(engine, state, action, n=300):
    """E[Y(action) - Y(no-op)] for the one-step outcome the engine is trained on:
    Y = d_profit + trust_multiplier * d_trust. profit_before and trust_before cancel; only demand noise is random.
    No-op = (price_change 0, ad_spend 0), i.e. the engine's T0 (note: that ZEROES the ad spend)."""
    def y(a):
        out = []
        for k in range(n):
            s = EcommerceSimulatorV5(initial_state=dict(state), seed=k)
            p0, t0 = s.state["profit"], s.state["brand_trust"]
            r = s.step(a)
            out.append((r["profit"] - p0) + engine.trust_multiplier * (r["brand_trust"] - t0))
        return float(np.mean(out))
    return y(action) - y({"price_change": 0.0, "ad_spend": 0.0})


def test_training_data_shape_and_columns(engine):
    df = engine.initial_train_history
    assert len(df) == 500 * 50
    assert {"initial_price", "initial_brand_trust", "initial_ad_spend", "season_phase", "price_change", "ad_spend",
            "trust_adjusted_profit_change", "profit_change", "trust_change", "sales_change"} <= set(df.columns)
    assert df.price_change.between(-0.40, 0.50).all() and df.ad_spend.between(0, 5000).all()
    np.testing.assert_allclose(df.trust_adjusted_profit_change,
                               df.profit_change + engine.trust_multiplier * df.trust_change, rtol=1e-9)


def test_data_regeneration_is_deterministic(engine, tmp_path):
    again = CausalEngineV6(data_path=str(tmp_path / "x.pkl"), force_regenerate=True)
    pd.testing.assert_frame_equal(engine.initial_train_history, again.initial_train_history)


STATES = [ctx(100, 500, .7, 10), ctx(80, 1500, .5, 30), ctx(120, 300, .9, 45), ctx(60, 3000, .6, 0), ctx(140, 800, .8, 20)]
ACTIONS = [{"price_change": pc, "ad_spend": ad} for pc in (-0.3, -0.1, 0.0, 0.1, 0.3) for ad in (0.0, 1500.0, 4000.0)]


@pytest.fixture(scope="module")
def quality(engine):
    rows = []
    for si, s in enumerate(STATES):
        for a in ACTIONS:
            rows.append(dict(state=si, price_change=a["price_change"], ad_spend=a["ad_spend"],
                             est=engine.estimate_causal_effect(a, s)["estimated_long_term_value"],
                             truth=true_effect(engine, s, a)))
    df = pd.DataFrame(rows)
    RESULTS.mkdir(exist_ok=True)
    df.to_csv(RESULTS / "causal_quality.csv", index=False)
    return df


def test_effect_rank_quality_vs_ground_truth(quality):
    rho = spearmanr(quality.est, quality.truth)[0]
    per_state = quality.groupby("state").apply(lambda g: spearmanr(g.est, g.truth)[0])
    print(f"\nspearman={rho:.3f}  per-state min={per_state.min():.3f}  sign-agree={(np.sign(quality.est) == np.sign(quality.truth)).mean():.3f}"
          f"  bias={(quality.est - quality.truth).mean():.0f}  rmse={np.sqrt(((quality.est - quality.truth) ** 2).mean()):.0f}"
          f"  truth_sd={quality.truth.std():.0f}")
    assert rho > 0.80                      # measured 0.87
    assert per_state.min() > 0.80          # measured 0.87


def test_effect_error_is_smaller_than_the_signal(quality):
    rmse = np.sqrt(((quality.est - quality.truth) ** 2).mean())
    assert rmse < quality.truth.std()      # measured 4.5k vs 7.7k: better than predicting the mean, not by a lot


def test_finding_estimated_effect_is_exactly_linear_in_treatment(engine):
    """FINDING: with continuous multi-treatment, CausalForestDML returns tau(x).t, so the estimate is odd and additive
    in (price_change, ad_spend), while the simulator is concave in ad spend. Hence est(no-op)=0 and
    est(-a) = -est(a) by construction -- the 'foresight' cannot represent diminishing returns or interactions."""
    s = STATES[0]
    e = lambda pc, ad: engine.estimate_causal_effect({"price_change": pc, "ad_spend": ad}, s)["estimated_long_term_value"]
    assert e(0.0, 0.0) == 0.0
    assert e(-0.2, 0.0) == pytest.approx(-e(0.2, 0.0), rel=1e-9)
    assert e(0.1, 2000.0) == pytest.approx(e(0.1, 0.0) + e(0.0, 2000.0), rel=1e-6)
    truth = lambda pc, ad: true_effect(engine, s, {"price_change": pc, "ad_spend": ad}, n=200)
    assert truth(0.0, 4000.0) - truth(0.0, 2000.0) < truth(0.0, 2000.0) - truth(0.0, 0.0)   # truth is concave in ad


def test_shap_additivity(engine):
    np.random.seed(0)                       # explain_decision draws an unseeded background sample
    out = engine.explain_decision(STATES[0], {"price_change": 0.1, "ad_spend": 1500.0})
    tau = engine.estimate_causal_effect({"price_change": 0.1, "ad_spend": 1500.0}, STATES[0])["estimated_long_term_value"]
    assert out["features"] == ["initial_price", "initial_brand_trust", "initial_ad_spend", "season_phase", "price_change", "ad_spend"]
    assert sum(out["shap_values"]) + out["base_value"] == pytest.approx(tau, rel=1e-6, abs=1e-6)


def test_retrain_grows_data_and_changes_model(engine):
    n0 = len(engine.initial_train_history)
    before = engine.estimate_causal_effect({"price_change": 0.1, "ad_spend": 1000.0}, STATES[0])["estimated_long_term_value"]
    exp = [dict(initial_price=100.0, initial_brand_trust=0.7, initial_ad_spend=500.0, season_phase=3, price_change=0.05,
                ad_spend=800.0, profit_change=1000.0 + 50 * i, trust_change=0.001 * i) for i in range(20)]
    engine.retrain(exp)
    assert len(engine.initial_train_history) == n0 + 20
    last = engine.initial_train_history.iloc[-1]
    assert last.trust_adjusted_profit_change == pytest.approx(last.profit_change + engine.trust_multiplier * last.trust_change)
    after = engine.estimate_causal_effect({"price_change": 0.1, "ad_spend": 1000.0}, STATES[0])["estimated_long_term_value"]
    assert after != before


def test_simulate_plan_summary_is_deterministic_and_ordered(engine):
    from src.components import SymbolicGuardianV4
    g = SymbolicGuardianV4()
    plan = [{"price_change": 0.0, "ad_spend": 500.0}] * 4
    a = engine.simulate_plan(EcommerceSimulatorV5(seed=0), g, ctx(100, 500, .7, 10), plan, n_rollouts=32, seed=1)
    b = engine.simulate_plan(EcommerceSimulatorV5(seed=0), g, ctx(100, 500, .7, 10), plan, n_rollouts=32, seed=1)
    assert a == b and a["horizon"] == 4 and a["rollouts"] == 32
    assert a["profit"]["p05"] <= a["profit"]["p50"] <= a["profit"]["p95"]
