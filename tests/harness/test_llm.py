"""LLM layer tests. MockLLM only — no network calls, matching the plan's test spec for M2."""

from __future__ import annotations

import pytest

from harness.llm.client import Usage
from harness.llm.faults import FaultInjectingClient
from harness.llm.meter import FALLBACK_PRICE, BudgetExceeded, Meter, price_for, reset_run_budget
from harness.llm.providers import AnthropicClient, OpenAIClient, OpenRouterClient, build_provider
from harness.llm.replay import ReplayClient, cache_key


class MockLLM:
    """Returns a fixed response the first N calls, then a *different* one — used to prove a
    replay cache serves the first response forever, not a live re-call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def complete_json(self, system, user, schema, timeout, **kwargs):
        self.calls += 1
        resp = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        return dict(resp), Usage(calls=1, tokens_in=100, tokens_out=50)


# ── provider selection ───────────────────────────────────────────────────────────

def test_build_provider_none_returns_none():
    assert build_provider("none", "any") is None


def test_build_provider_routes_by_name(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert isinstance(build_provider("openrouter", "m"), OpenRouterClient)
    assert isinstance(build_provider("openai", "m"), OpenAIClient)
    assert isinstance(build_provider("anthropic", "m"), AnthropicClient)


def test_build_provider_unknown_raises():
    with pytest.raises(ValueError):
        build_provider("not-a-provider", "m")


# ── replay determinism ──────────────────────────────────────────────────────────

def test_replay_cache_key_is_stable_and_sensitive_to_inputs():
    a = cache_key("L1", "1", "model-x", "sys", "usr", "1", 0)
    b = cache_key("L1", "1", "model-x", "sys", "usr", "1", 0)
    c = cache_key("L1", "1", "model-x", "sys", "usr2", "1", 0)
    assert a == b and a != c


def test_replay_cache_key_is_sensitive_to_model():
    a = cache_key("L1", "1", "model-x", "sys", "usr", "1", 0)
    b = cache_key("L1", "1", "model-y", "sys", "usr", "1", 0)
    assert a != b, "a cache recorded for one model must not be replayed for another"


def test_replay_record_then_replay_is_deterministic(tmp_path):
    mock = MockLLM([{"v": 1}, {"v": 2}, {"v": 3}])
    recorder = ReplayClient(mock, tmp_path, "record")
    first, _ = recorder.complete_json("sys", "usr", {"properties": {}}, 5.0, leaf="L1", prompt_ver="1",
                                      schema_ver="1", replicate=0)
    assert first == {"v": 1} and mock.calls == 1

    # same key, record mode: a cache hit, no second call to the (would-be different) mock
    second, _ = recorder.complete_json("sys", "usr", {"properties": {}}, 5.0, leaf="L1", prompt_ver="1",
                                       schema_ver="1", replicate=0)
    assert second == {"v": 1} and mock.calls == 1

    replayer = ReplayClient(mock, tmp_path, "replay")
    third, _ = replayer.complete_json("sys", "usr", {"properties": {}}, 5.0, leaf="L1", prompt_ver="1",
                                      schema_ver="1", replicate=0)
    assert third == {"v": 1} and mock.calls == 1


def test_replay_mode_fails_fast_on_cache_miss(tmp_path):
    mock = MockLLM([{"v": 1}])
    replayer = ReplayClient(mock, tmp_path, "replay")
    with pytest.raises(FileNotFoundError):
        replayer.complete_json("sys", "usr", {"properties": {}}, 5.0, leaf="L1", prompt_ver="1",
                               schema_ver="1", replicate=0)


def test_replay_live_mode_always_calls_and_never_caches(tmp_path):
    mock = MockLLM([{"v": 1}, {"v": 2}])
    live = ReplayClient(mock, tmp_path, "live")
    a, _ = live.complete_json("sys", "usr", {"properties": {}}, 5.0, leaf="L1", prompt_ver="1",
                              schema_ver="1", replicate=0)
    b, _ = live.complete_json("sys", "usr", {"properties": {}}, 5.0, leaf="L1", prompt_ver="1",
                              schema_ver="1", replicate=0)
    assert a == {"v": 1} and b == {"v": 2} and mock.calls == 2
    assert list(tmp_path.iterdir()) == []


def test_invalid_mode_raises():
    with pytest.raises(ValueError):
        ReplayClient(MockLLM([{}]), "/tmp", "bogus")


def test_replay_cache_hit_still_credits_the_wrapped_meter(tmp_path):
    """Regression test for a real bug (found by an independent review, not by a test originally):
    a cache hit returned the cached Usage to the caller but never touched the wrapped Meter's
    running total, so `usage_of()`/the trace undercounted cost for anything served from cache."""
    mock = MockLLM([{"v": 1}])
    meter = Meter(mock, "claude-sonnet", max_usd_per_run=100.0)
    recorder = ReplayClient(meter, tmp_path, "record")
    recorder.complete_json("sys", "usr", {"properties": {}}, 5.0, leaf="L1", prompt_ver="1", schema_ver="1")
    assert meter.usage.calls == 1  # the live miss credited it

    # second call, same key: a cache hit (record mode) -- must still credit the Meter
    recorder.complete_json("sys", "usr", {"properties": {}}, 5.0, leaf="L1", prompt_ver="1", schema_ver="1")
    assert meter.usage.calls == 2
    assert meter.usage.cost_usd > 0

    replayer = ReplayClient(meter, tmp_path, "replay")
    replayer.complete_json("sys", "usr", {"properties": {}}, 5.0, leaf="L1", prompt_ver="1", schema_ver="1")
    assert meter.usage.calls == 3


# ── meter budget enforcement ──────────────────────────────────────────────────────

def test_meter_tracks_usage_and_cost():
    mock = MockLLM([{"v": 1}])
    meter = Meter(mock, "claude-sonnet", max_usd_per_run=100.0)
    _, usage = meter.complete_json("sys", "usr", {}, 5.0)
    price = price_for("claude-sonnet")
    expected = (100 * price["in"] + 50 * price["out"]) / 1e6
    assert usage.cost_usd == pytest.approx(expected)
    assert meter.usage.calls == 1


def test_price_for_glm_flashx_is_not_the_flat_fallback():
    """Regression test: before this row existed, z-ai/glm-5.3-flashx (the model actually
    configured in .env, and the one used for the first real LLM-arm run) fell back to the
    Claude-Sonnet-rate placeholder ($3/$15 per M tokens) — about 8-12x this model's real
    OpenRouter price, overstating every cost figure a run with it produced by the same factor."""
    price = price_for("z-ai/glm-5.3-flashx")
    assert price == {"in": 0.37, "out": 1.25}
    assert price != FALLBACK_PRICE


def test_meter_raises_budget_exceeded():
    mock = MockLLM([{"v": 1}] * 10)
    meter = Meter(mock, "claude-opus", max_usd_per_run=0.0001)  # near-zero budget
    with pytest.raises(BudgetExceeded):
        meter.complete_json("sys", "usr", {}, 5.0)


def test_meter_budget_is_per_run_not_per_lifetime():
    """Regression test for a real bug (found by an independent review): the budget check used to
    compare against the lifetime `usage` total, so across a multi-run simulate() call (one Meter,
    many runs) a budget meant to apply per run actually applied once across the whole simulation.
    `run_usage` resets via `reset_run()`/`reset_run_budget()`; `usage` keeps growing."""
    mock = MockLLM([{"v": 1}] * 10)
    price = price_for("claude-opus")
    per_call_cost = (100 * price["in"] + 50 * price["out"]) / 1e6
    budget = per_call_cost * 1.5  # room for one call per run, not two
    meter = Meter(mock, "claude-opus", max_usd_per_run=budget)

    meter.complete_json("sys", "usr", {}, 5.0)  # run 1's only call: fine
    with pytest.raises(BudgetExceeded):
        meter.complete_json("sys", "usr", {}, 5.0)  # run 1's second call: over budget

    meter.reset_run()
    meter.complete_json("sys", "usr", {}, 5.0)  # run 2's first call: fine again, budget reset
    assert meter.usage.calls == 3  # lifetime total keeps growing regardless
    assert meter.run_usage.calls == 1  # run-level total reset


def test_reset_run_budget_walks_the_stack_to_the_meter():
    mock = MockLLM([{"v": 1}] * 5)
    price = price_for("claude-opus")
    budget = (100 * price["in"] + 50 * price["out"]) / 1e6 * 1.5
    meter = Meter(mock, "claude-opus", budget)
    faulted = FaultInjectingClient(meter, "")  # a layer with no reset_run of its own

    faulted.complete_json("sys", "usr", {}, 5.0)
    with pytest.raises(BudgetExceeded):
        faulted.complete_json("sys", "usr", {}, 5.0)

    reset_run_budget(faulted)
    faulted.complete_json("sys", "usr", {}, 5.0)  # didn't raise: the reset reached the Meter


def test_reset_run_budget_is_a_noop_for_none_or_no_meter():
    reset_run_budget(None)              # must not raise
    reset_run_budget(MockLLM([{"v": 1}]))  # no .reset_run anywhere in the chain; must not raise


def test_meter_with_no_provider_raises():
    meter = Meter(None, "m", 1.0)
    with pytest.raises(RuntimeError):
        meter.complete_json("sys", "usr", {}, 5.0)


# ── fault injection ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("mode,exc", [("timeout", TimeoutError), ("exception", RuntimeError),
                                      ("budget", BudgetExceeded)])
def test_fault_modes_raise(mode, exc):
    client = FaultInjectingClient(MockLLM([{"v": 1}]), mode)
    with pytest.raises(exc):
        client.complete_json("sys", "usr", {"properties": {}}, 5.0)


def test_fault_malformed_returns_unparseable_payload():
    client = FaultInjectingClient(MockLLM([{"v": 1}]), "malformed")
    resp, usage = client.complete_json("sys", "usr", {"properties": {"x": {"type": "number"}}}, 5.0)
    assert resp == {"_fault": "malformed"}


def test_fault_out_of_range_fills_every_property_with_an_extreme_value():
    schema = {"properties": {"n": {"type": "number"}, "s": {"type": "string"}, "b": {"type": "boolean"}}}
    client = FaultInjectingClient(MockLLM([{"v": 1}]), "out_of_range")
    resp, _ = client.complete_json("sys", "usr", schema, 5.0)
    assert resp["n"] == 1e12 and resp["b"] is True and len(resp["s"]) > 1000


def test_fault_passthrough_when_unset():
    client = FaultInjectingClient(MockLLM([{"v": 42}]), "")
    resp, _ = client.complete_json("sys", "usr", {"properties": {}}, 5.0)
    assert resp == {"v": 42}


def test_invalid_fault_mode_raises():
    with pytest.raises(ValueError):
        FaultInjectingClient(MockLLM([{}]), "not-a-real-fault")
