"""Fast checks on the sandbox's invariants (≈1 min)."""

import numpy as np
import pandas as pd
import pytest

from gpc.guardrails import apply_guardrails
from gpc.market import Market, _slot_shares
from gpc.runner import ROAS_TOLERANCE, simulate
from gpc.observation import Observation
from gpc.policy import NoOpPolicy
from gpc.world import SLOTS, WARMUP_DAYS, build_world


def test_world_shape():
    w = build_world()
    p = w.public
    assert len(p["products"]) == 5 and len(p["cities"]) == 5 and len(p["keywords"]) == 10
    assert len(p["campaigns"]) == 25
    assert (p["campaigns"].groupby(["sku_id", "city_id"]).size() == 1).all()       # 1 SKU × 1 city
    assert "incrementality" not in p["keywords"].columns                          # truth stays hidden


def test_slot_shares_are_a_distribution_and_monotone_in_bid():
    base = {1: 300.0, 5: 280.0, 9: 255.0, 13: 225.0}
    lo, hi = _slot_shares(250, base, 0.3), _slot_shares(450, base, 0.3)
    assert sum(s for s, _ in lo.values()) <= 1 + 1e-9
    assert hi[1][0] > lo[1][0]                                                    # bid more → top slot more often
    assert hi[1][1] > lo[1][1]                                                    # … and pay more for it


def test_common_random_numbers():
    w = build_world()
    m = Market(w)
    a = m.simulate_day(3, w.public["campaigns"], w.public["campaign_keywords"])
    b = m.simulate_day(3, w.public["campaigns"], w.public["campaign_keywords"])
    pd.testing.assert_frame_equal(a["sku_city_daily"], b["sku_city_daily"])


@pytest.fixture(scope="module")
def warm_obs():
    w = build_world()
    m = Market(w)
    acc = {"daily_facts": [], "campaign_daily": [], "sku_city_daily": []}
    for d in range(WARMUP_DAYS):
        for k, v in m.simulate_day(d, w.public["campaigns"], w.public["campaign_keywords"]).items():
            acc[k].append(v)
    fr = {k: pd.concat(v, ignore_index=True) for k, v in acc.items()}
    roas = fr["daily_facts"].ad_revenue_inr.sum() / fr["daily_facts"].spend_inr.sum()
    return Observation(run=1, day=WARMUP_DAYS, public=w.public, campaigns=w.public["campaigns"],
                       campaign_keywords=w.public["campaign_keywords"], roas_floor=roas * (1 - ROAS_TOLERANCE),
                       warmup_droas=roas, **fr)


def test_guardrails_block_and_clamp(warm_obs):
    ck = warm_obs.campaign_keywords.iloc[0]
    acts = pd.DataFrame([
        {"campaign_id": "C-NOPE", "keyword_id": "", "action_type": "increase_budget", "new_value": 9e9},
        {"campaign_id": ck.campaign_id, "keyword_id": ck.keyword_id, "action_type": "reduce_cpm", "new_value": 1.0},
        {"campaign_id": ck.campaign_id, "keyword_id": ck.keyword_id, "action_type": "reduce_cpm", "new_value": 150.0},
        {"campaign_id": ck.campaign_id, "keyword_id": "", "action_type": "set_dayparts", "new_value": ""},
    ])
    final, log, _ = apply_guardrails(warm_obs, acts)
    rules = set(zip(log.rule, log.outcome))
    assert ("G0_SCHEMA", "blocked") in rules
    assert ("G1_BID_BOUNDS", "clamped") in rules or ("G2_BID_STEP", "clamped") in rules
    assert len(final) == 1 and final.iloc[0].new_value >= 200


def test_no_op_is_a_valid_policy():
    res = simulate(build_world(), NoOpPolicy(), n_runs=1)
    assert len(res.runs) == 1 and len(res.runs[0]["final"]) == 0
