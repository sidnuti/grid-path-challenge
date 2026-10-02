"""S1-S10 scenario tests (plan section "Tests", M3). Each asserts a *behaviour*, never a dev
magnitude, on either the dev warm-up observation as-is (picking a real cell that already has the
needed shape — e.g. S1 needs a slot-1-dominant brand cell, and the dev data has several) or a
constructed perturbation of it (S6 forces a low-OSA window that doesn't occur in the unmodified
dev warm-up).

Two scenarios are implemented slightly differently from their one-line description in the plan,
logged here rather than silently reinterpreted:

- **S2** ("a competitor miss is cut >= 20% at once and redeployed"): this scenario's premise
  turned out to be built on a backwards reading of E1 (competitor keywords are the *most*
  incremental lever, not the least — see `harness/htn/methods.py`'s docstring for the full
  correction) and the special-cased fast cut it specified has been removed. The test now checks
  the opposite of the original plan: that a competitor MISSES cell is cut through the exact same
  ladder-paced path as everything else, no special case at all. Also, independent of that
  correction, this harness never modelled a transport/redeploy step for cuts (see
  `harness/tools/sizing.py`'s docstring on the plan's dropped `linprog` step) — a cut's freed
  money was never tracked to a specific destination, so "redeployed" was never literally true here
  even before the incrementality fix.
- **S8** ("retreat on a price shock"): implemented as "do not chase a price-shock cell with a
  surge raise" (`shock_raises` only acts on `direction == "surge"`) rather than an active cut —
  there is no mechanical signal in this build that a *price* shock (as opposed to a demand drop)
  should trigger a cut beyond what the normal MISSES ladder already does.
"""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from gpc.engine.grid import build_grid
from gpc.market import Market
from gpc.observation import Observation
from gpc.policy import DeterministicTraversal
from gpc.world import WARMUP_DAYS, build_world

from harness.config import load_params
from harness.htn.llm_methods import explore_candidates, shock_raises
from harness.htn.methods import m_base_cuts, m_budget_raises, m_reprice_raises, m_sibling_holds
from harness.llm.client import Usage
from harness.policy import HTNHarness, HTNToolsOnly, _harness_recommend
from harness.tools.features import diagnose
from harness.tools.headroom import compute_headroom
from harness.tools.incrementality import iota_lookup
from harness.tools.precheck import precheck
from harness.tools.siblings import markets


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


class MockLLM:
    """Returns `answers[field]` for any field named in the schema, else a type-appropriate
    neutral default — lets each scenario force exactly the judgment it needs to test."""

    def __init__(self, answers: dict):
        self.answers = answers

    def complete_json(self, system, user, schema, timeout, **kwargs):
        out = {}
        for name, prop in schema.get("properties", {}).items():
            if name in self.answers:
                out[name] = self.answers[name]
                continue
            t = prop.get("type")
            out[name] = False if t == "boolean" else ("" if t == "string" else 0.0)
        return out, Usage(calls=1, tokens_in=20, tokens_out=10)


def test_s1_no_raise_on_a_slot1_brand_cell(warm_obs):
    diag = diagnose(warm_obs)
    mk = markets(warm_obs, diag.grid)
    dominant = mk[mk.slot1_share_7d >= 0.80]
    assert len(dominant), "fixture should have at least one slot-1-dominant cell"
    row = dominant.iloc[0]
    passed, reason = precheck(warm_obs, diag.verdicts, diag.pacing,
                              {"campaign_id": row.campaign_id, "keyword_id": row.keyword_id,
                               "action_type": "increase_cpm", "new_value": 9999.0})
    assert not passed and reason.startswith("G3")


def test_s2_competitor_misses_are_cut_on_the_same_ladder_as_everything_else(warm_obs):
    """Regression guard for a real bug, not a behaviour spec: an earlier `M_CompetitorCut` cut
    competitor MISSES cells straight to the best-dROAS option, skipping the patience ladder, on
    the claim that competitor keywords have ~0 incrementality so a fast cut is ~free. E1 says the
    opposite — competitor beta ~0 means iota ~1, the *highest* incrementality in the portfolio —
    so that premise was backwards and the method was removed (`harness/htn/methods.py`'s
    docstring has the full story). This test pins down that competitor MISSES cells now go
    through the exact same `m_base_cuts` ladder-paced path as brand/generic — i.e. that the
    now-removed special case doesn't quietly come back."""
    kt = warm_obs.public["keywords"].set_index("keyword_id").keyword_type
    diag = diagnose(warm_obs)
    cuts = m_base_cuts(warm_obs, diag)
    competitor_cuts = cuts[cuts.keyword_id.map(kt) == "competition"]
    assert len(competitor_cuts), "fixture should have at least one MISSES competitor cell"
    bids = diag.bids.set_index(["campaign_id", "keyword_id"])
    for c in competitor_cuts.itertuples():
        b = bids.loc[(c.campaign_id, c.keyword_id)]
        assert c.new_value == pytest.approx(b.chosen_bid), "competitor cuts must use the engine's own ladder-paced choice"
        assert f"M_Base: {b.reason}" == c.reason


def test_s3_followers_hold_and_the_leader_can_raise(warm_obs):
    params = load_params()
    diag = diagnose(warm_obs)
    hold, mk = m_sibling_holds(warm_obs, diag, params)
    assert hold, "fixture should have at least one held follower"
    iota = iota_lookup(warm_obs)
    reprice = m_reprice_raises(warm_obs, diag, hold, iota)
    raised_keys = set(zip(reprice.campaign_id, reprice.keyword_id))
    assert not (raised_keys & hold), "a held follower must never appear in the raise candidates"


def test_s4_budget_raise_only_when_campaign_clears_spend_weighted_roas(warm_obs):
    params = load_params()
    diag = diagnose(warm_obs)
    iota = iota_lookup(warm_obs)
    budget = m_budget_raises(warm_obs, diag, params, iota)
    for b in budget.itertuples():
        cv = diag.verdicts[diag.verdicts.campaign_id == b.campaign_id]
        sw = cv.spend_7d_avg.sum()
        w = cv.spend_7d_avg / sw
        shrunk_w = float((cv.droas_shrunk.fillna(0) * w).sum())
        goal_w = float((cv.goal_droas * w).sum())
        assert shrunk_w >= 0.9 * goal_w, "M_Budget must only propose a raise that would pass G7"
        passed, _ = precheck(warm_obs, diag.verdicts, diag.pacing,
                             {"campaign_id": b.campaign_id, "keyword_id": "", "action_type": "increase_budget",
                              "new_value": b.new_value})
        assert passed


def test_s5_confirmed_surge_raises_a_cell_even_if_its_verdict_is_stale(warm_obs):
    diag = diagnose(warm_obs)
    row = diag.bids[diag.bids.verdict != "CLEARS"].iloc[0]
    shocks = pd.DataFrame([{"campaign_id": row.campaign_id, "keyword_id": row.keyword_id, "z_reach": 4.0,
                            "z_cpm": 0.0, "z_osa": 0.0, "shock_reach": True, "shock_cpm": False,
                            "shock_osa_drop": False, "direction": "surge", "own_action_confound": False}])
    llm = MockLLM({"is_shock": True, "direction": "surge", "confidence": 0.9})
    iota = iota_lookup(warm_obs)
    out = shock_raises(warm_obs, diag, shocks, llm, iota)
    assert len(out) == 1
    assert out.iloc[0].new_value > out.iloc[0].current_value


def test_s6_no_increase_during_a_low_osa_window(warm_obs):
    low = warm_obs.sku_city_daily.copy()
    mask = (low.sku_id == "S1") & (low.city_id == "DEL") & (low.day >= warm_obs.day - 3)
    low.loc[mask, "osa"] = 0.30
    perturbed = dataclasses.replace(warm_obs, sku_city_daily=low)
    diag = diagnose(perturbed)
    passed, reason = precheck(perturbed, diag.verdicts, diag.pacing,
                              {"campaign_id": "C-S1-DEL", "keyword_id": "K01", "action_type": "increase_cpm",
                               "new_value": 9999.0})
    assert not passed and reason.startswith("G4")


def test_s7_exploration_is_capped(warm_obs):
    params = load_params()
    params = dataclasses.replace(params, explore_enabled=True, explore_max_thin_cells=1,
                                 explore_spend_cap_inr_day=400.0)
    diag = diagnose(warm_obs)
    assert (diag.bids.verdict == "THIN").sum() >= 2, "fixture should have >= 2 THIN cells to cap over"
    llm = MockLLM({"explore": True, "max_spend_inr_day": 10_000.0})  # asks for more than the cap allows
    out = explore_candidates(warm_obs, diag, params, llm)
    assert len(out) <= 1
    if len(out):
        opt_spend = diag.options[(diag.options.campaign_id == out.iloc[0].campaign_id)
                                 & (diag.options.keyword_id == out.iloc[0].keyword_id)
                                 & (diag.options.bid == out.iloc[0].new_value)].pred_spend
        assert float(opt_spend.iloc[0]) <= params.explore_spend_cap_inr_day + 1e-6


def test_s8_a_price_drop_shock_does_not_trigger_a_surge_raise(warm_obs):
    diag = diagnose(warm_obs)
    row = diag.bids[diag.bids.verdict != "CLEARS"].iloc[0]
    shocks = pd.DataFrame([{"campaign_id": row.campaign_id, "keyword_id": row.keyword_id, "z_reach": -4.0,
                            "z_cpm": 3.0, "z_osa": 0.0, "shock_reach": True, "shock_cpm": True,
                            "shock_osa_drop": False, "direction": "drop", "own_action_confound": False}])
    llm = MockLLM({"is_shock": True, "direction": "drop", "confidence": 0.9})
    iota = iota_lookup(warm_obs)
    out = shock_raises(warm_obs, diag, shocks, llm, iota)
    assert len(out) == 0


def test_s9_llm_exception_falls_back_to_baseline(warm_obs, monkeypatch):
    class ExplodingLLM:
        def complete_json(self, *a, **kw):
            raise RuntimeError("provider is down")

    params = load_params()
    params = dataclasses.replace(params, depth="L1")

    def boom(*args, **kwargs):
        raise RuntimeError("simulated catastrophic failure inside _harness_recommend")

    monkeypatch.setattr("harness.policy.detect_shocks", boom)
    policy = HTNHarness(params=params, llm=ExplodingLLM())
    actions = policy.recommend(warm_obs)
    assert policy.last_trace.get("fallback_reason") == "exception"
    baseline = DeterministicTraversal().recommend(warm_obs)
    pd.testing.assert_frame_equal(actions.reset_index(drop=True), baseline.reset_index(drop=True))


def test_s9b_individual_leaf_failures_do_not_trigger_the_coarse_fallback(warm_obs):
    """The finer-grained fail-soft: a leaf exception should be absorbed by `leaf()` and behave
    like llm=None for that judgment, not escalate to the whole-policy baseline fallback."""
    class ExplodingLLM:
        def complete_json(self, *a, **kw):
            raise RuntimeError("provider is down")

    params = load_params()
    params = dataclasses.replace(params, depth="L1")
    policy = HTNHarness(params=params, llm=ExplodingLLM())
    actions = policy.recommend(warm_obs)
    assert "fallback_reason" not in (policy.last_trace or {})
    tools_only = HTNToolsOnly(params).recommend(warm_obs)
    pd.testing.assert_frame_equal(actions.reset_index(drop=True), tools_only.reset_index(drop=True))


def test_s10_the_last_run_spends_the_full_remaining_headroom():
    params = load_params()
    w = build_world(7)
    m = Market(w)
    acc = {"daily_facts": [], "campaign_daily": [], "sku_city_daily": []}
    for d in range(WARMUP_DAYS + 35):  # through run 6's decision day (28 + 5*7)
        for k, v in m.simulate_day(d, w.public["campaigns"], w.public["campaign_keywords"]).items():
            acc[k].append(v)
    fr = {k: pd.concat(v, ignore_index=True) for k, v in acc.items()}
    warm = float(fr["daily_facts"][fr["daily_facts"].day < WARMUP_DAYS].pipe(
        lambda f: f.ad_revenue_inr.sum() / f.spend_inr.sum()))
    obs_run6 = Observation(run=6, day=WARMUP_DAYS + 35, public=w.public, campaigns=w.public["campaigns"],
                           campaign_keywords=w.public["campaign_keywords"], roas_floor=warm * 0.98,
                           warmup_droas=warm, **fr)
    obs_run5 = dataclasses.replace(obs_run6, run=5)
    h6 = compute_headroom(obs_run6, params)
    h5 = compute_headroom(obs_run5, params)
    assert h6.allowance_inr_day == pytest.approx(h6.headroom_inr_day)
    if h5.headroom_inr_day > 0:
        assert h5.allowance_inr_day < h5.headroom_inr_day
