"""Unit tests for `harness/tools/*`, against dev-scenario warm-up data and synthetic panels.
No network, no slow sims (`gpc.market.simulate_day` over the warm-up is the slowest thing here,
and it is in-process and deterministic — see `test_common_random_numbers` in the base sandbox)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gpc.engine.grid import build_grid
from gpc.guardrails import apply_guardrails
from gpc.market import Market
from gpc.observation import Observation
from gpc.world import WARMUP_DAYS, build_world

from harness.tools.headroom import compute_headroom
from harness.tools.incrementality import fit_type_incrementality
from harness.tools.precheck import precheck
from harness.tools.siblings import contested_markets, markets
from harness.config import load_params


@pytest.fixture(scope="module")
def warm_obs():
    w = build_world(7)
    m = Market(w)
    acc = {"daily_facts": [], "campaign_daily": [], "sku_city_daily": []}
    for d in range(WARMUP_DAYS):
        for k, v in m.simulate_day(d, w.public["campaigns"], w.public["campaign_keywords"]).items():
            acc[k].append(v)
    fr = {k: pd.concat(v, ignore_index=True) for k, v in acc.items()}
    warm = float(fr["daily_facts"].ad_revenue_inr.sum() / fr["daily_facts"].spend_inr.sum())
    return Observation(run=1, day=WARMUP_DAYS, public=w.public, campaigns=w.public["campaigns"],
                       campaign_keywords=w.public["campaign_keywords"], roas_floor=warm * 0.98,
                       warmup_droas=warm, **fr)


# ── incrementality ──────────────────────────────────────────────────────────────

def test_incrementality_recovers_known_coefficients_on_synthetic_data():
    """Construct a panel where organic units are a known linear function of ad orders per type,
    with no noise, and check lstsq recovers the coefficients within a small tolerance."""
    rng = np.random.default_rng(0)
    true_beta = {"brand": -0.88, "generic": -0.50, "competition": 0.0}
    rows = []
    for sku in ["S1", "S2"]:
        for city in ["DEL", "MUM"]:
            base = rng.uniform(40, 60)
            for day in range(60):
                orders = {t: rng.uniform(0, 20) for t in true_beta}
                organic = base + 0.3 * (day % 7) + sum(true_beta[t] * orders[t] for t in true_beta)
                row = {"sku_id": sku, "city_id": city, "day": day, "organic_units": organic}
                row.update({f"ad_orders_{t}": orders[t] for t in true_beta})
                rows.append(row)
    panel = pd.DataFrame(rows)
    from harness.tools.incrementality import _fit_ols
    panel["dow"] = panel.day % 7
    betas = _fit_ols(panel, list(true_beta), fe_cols=["sku_id", "city_id", "dow"])
    for t, b in true_beta.items():
        assert abs(betas[t] - b) < 0.06, (t, betas[t], b)  # finite-sample FE noise, not model bias


def test_incrementality_ordering_on_dev(warm_obs):
    df = fit_type_incrementality(warm_obs).set_index("keyword_type").iota
    assert df["brand"] < df["generic"] < df["competition"] + 1e-9 or df["brand"] < df["generic"] <= df["competition"]


# ── siblings ─────────────────────────────────────────────────────────────────────

def test_siblings_contested_markets_on_dev(warm_obs):
    grid = build_grid(warm_obs)
    mk = markets(warm_obs, grid)
    cm = contested_markets(mk)
    assert len(cm) == 40          # 40 of the 50 city x keyword markets have >= 2 Aurel siblings
    assert mk.is_contested.sum() == 100


# ── headroom ─────────────────────────────────────────────────────────────────────

def test_headroom_arithmetic_is_nonnegative_and_matches_formula(warm_obs):
    params = load_params()
    h = compute_headroom(warm_obs, params)
    assert h.headroom_inr_day >= 0
    # allowance is a fraction of banked headroom, floored at headroom_min_allowance_inr_day (run 1
    # has 0 banked headroom by construction -- no post-warmup data exists yet -- so the min floor
    # is expected to dominate here; see headroom.py's module docstring for why that's intentional)
    assert h.allowance_inr_day <= max(h.headroom_inr_day, params.headroom_min_allowance_inr_day) + 1e-6
    assert h.allowance_inr_day >= 0


def test_headroom_run1_gets_the_minimum_allowance_floor_not_zero(warm_obs):
    """Regression test for a real limitation an independent review flagged: run 1 has zero banked
    post-warmup headroom by construction, so the pure formula always gives $0 and sizing could
    never consider a raise in the first run of any simulation, however safe. `gpc.guardrails`' G8
    remains the actual floor backstop regardless of this minimum."""
    params = load_params()
    h = compute_headroom(warm_obs, params)  # warm_obs fixture is run=1
    assert h.headroom_inr_day == 0.0
    assert h.allowance_inr_day == params.headroom_min_allowance_inr_day


# ── precheck vs apply_guardrails ───────────────────────────────────────────────────

def test_precheck_matches_guardrails_on_randomized_actions(warm_obs):
    from harness.tools.features import diagnose
    rng = np.random.default_rng(1)
    diag = diagnose(warm_obs)
    cks = warm_obs.campaign_keywords[warm_obs.campaign_keywords.active].sample(30, random_state=1)
    rows = []
    for ck in cks.itertuples():
        kind = rng.choice(["increase_cpm", "increase_budget"])
        if kind == "increase_cpm":
            rows.append({"campaign_id": ck.campaign_id, "keyword_id": ck.keyword_id, "action_type": "increase_cpm",
                        "new_value": ck.bid_cpm_inr * 1.2})
        else:
            budget = float(warm_obs.campaigns.set_index("campaign_id").loc[ck.campaign_id, "daily_budget_inr"])
            rows.append({"campaign_id": ck.campaign_id, "keyword_id": "", "action_type": "increase_budget",
                        "new_value": budget * 1.3})
    actions = pd.DataFrame(rows).drop_duplicates(["campaign_id", "keyword_id", "action_type"])
    final, log, _ = apply_guardrails(warm_obs, actions, diag.grid)
    passed_keys = {(r.campaign_id, r.keyword_id, r.action_type) for r in final.itertuples()}
    for a in actions.to_dict("records"):
        would_pass, _ = precheck(warm_obs, diag.verdicts, diag.pacing, a)
        key = (a["campaign_id"], a["keyword_id"], a["action_type"])
        # precheck only covers G0/G3/G4/G5/G7 (not G1/G2/G6 clamps or G8 portfolio trims), so a
        # precheck pass may still be clamped or G8-trimmed by apply_guardrails — but a precheck
        # *fail* must never be something apply_guardrails actually shipped unclamped.
        if not would_pass:
            assert key not in passed_keys, f"precheck blocked {key} but apply_guardrails shipped it"
