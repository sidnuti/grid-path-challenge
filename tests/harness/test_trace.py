"""`harness/trace/*`: off by default (`TRACE_DIR` unset), and a round-trippable JSONL record of
exactly what a run already computed when it is on."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from gpc.market import Market
from gpc.observation import Observation
from gpc.world import WARMUP_DAYS, build_world

from harness.config import load_params
from harness.tools.headroom import compute_headroom
from harness.trace.schema import build_trace
from harness.trace.writer import maybe_write_trace, read_traces, trace_dir


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


def test_trace_dir_unset_means_off(monkeypatch):
    monkeypatch.delenv("TRACE_DIR", raising=False)
    assert trace_dir() is None


def test_trace_dir_empty_string_means_off(monkeypatch):
    monkeypatch.setenv("TRACE_DIR", "")
    assert trace_dir() is None


def test_maybe_write_trace_is_a_noop_when_off(warm_obs, monkeypatch):
    monkeypatch.delenv("TRACE_DIR", raising=False)
    params = load_params()
    actions = pd.DataFrame(columns=["campaign_id", "keyword_id", "action_type", "new_value", "reason"])
    result = maybe_write_trace("test_policy", warm_obs, params, None, actions, {})
    assert result is None


def test_build_trace_counts_match_run_trace(warm_obs):
    params = load_params()
    headroom = compute_headroom(warm_obs, params)
    actions = pd.DataFrame([{"campaign_id": "C-S1-DEL", "keyword_id": "K01", "action_type": "increase_cpm",
                            "new_value": 300.0, "reason": "test"}])
    run_trace = {"depth": "L1", "headroom": headroom, "candidates_raised": pd.DataFrame({"x": [1, 2, 3]}),
                "candidates_cut": pd.DataFrame({"x": [1]}), "candidates_explore": pd.DataFrame(),
                "precheck_dropped": pd.DataFrame({"x": [1, 2]}), "leaf_calls": [{"leaf": "L1_value", "outcome": "ok"}]}
    trace = build_trace("htn_harness", warm_obs, params, None, actions, run_trace)
    assert trace.depth == "L1"
    assert trace.n_candidates_raised == 3
    assert trace.n_candidates_cut == 1
    assert trace.n_candidates_explore == 0
    assert trace.n_precheck_dropped == 2
    assert trace.n_actions_shipped == 1
    assert len(trace.leaf_calls) == 1
    assert trace.headroom["allowance_inr_day"] == headroom.allowance_inr_day
    assert trace.fallback_reason is None


def test_obs_digest_deterministic_and_sensitive_to_changes(warm_obs):
    import dataclasses
    from harness.trace.schema import _obs_digest
    d1 = _obs_digest(warm_obs)
    d2 = _obs_digest(warm_obs)
    assert d1 == d2
    changed_ck = warm_obs.campaign_keywords.copy()
    changed_ck.loc[changed_ck.index[0], "bid_cpm_inr"] += 1.0
    other = dataclasses.replace(warm_obs, campaign_keywords=changed_ck)
    assert _obs_digest(other) != d1


def test_maybe_write_trace_roundtrips_through_jsonl(warm_obs, tmp_path, monkeypatch):
    monkeypatch.setenv("TRACE_DIR", str(tmp_path))
    params = load_params()
    actions = pd.DataFrame(columns=["campaign_id", "keyword_id", "action_type", "new_value", "reason"])
    written = maybe_write_trace("test_policy", warm_obs, params, None, actions, {"depth": "L0"})
    assert written is not None
    path = tmp_path / "test_policy.jsonl"
    assert path.exists()
    loaded = read_traces(path)
    assert len(loaded) == 1
    assert loaded[0].policy == "test_policy"
    assert loaded[0].run == warm_obs.run


def test_maybe_write_trace_appends_across_calls(warm_obs, tmp_path, monkeypatch):
    monkeypatch.setenv("TRACE_DIR", str(tmp_path))
    params = load_params()
    actions = pd.DataFrame(columns=["campaign_id", "keyword_id", "action_type", "new_value", "reason"])
    maybe_write_trace("p", warm_obs, params, None, actions, {"depth": "L0"})
    maybe_write_trace("p", warm_obs, params, None, actions, {"depth": "L0"})
    lines = (tmp_path / "p.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        json.loads(line)  # each line is independently valid JSON
