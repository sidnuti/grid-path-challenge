"""Offline tests for the record/replay transport + ledger (no network: the inner transport is mocked)."""
import json

import httpx
import pytest

from common import ledger, openrouter as orr

pytestmark = pytest.mark.offline


def _fake_inner(counter):
    def handler(request):
        counter["n"] += 1
        body = json.loads(request.content)
        return httpx.Response(200, json={
            "id": "x", "model": body["model"],
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": f"r{counter['n']}"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}})
    return httpx.MockTransport(handler)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    calls = {"n": 0}

    def make(mode, item="p0_ping", salt=""):
        t = orr.CachingTransport(item, salt, cache_dir=tmp_path / "cache", mode_=mode)
        t._inner = _fake_inner(calls)
        from openai import OpenAI
        return OpenAI(api_key="k", base_url=orr.BASE_URL, http_client=httpx.Client(transport=t), max_retries=0)
    return make, calls


def ask(c, model="qwen/qwen3.7-flash", prompt="hi"):
    return c.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}], max_tokens=8)


def test_replay_miss_is_hard_error(env):
    make, calls = env
    with pytest.raises(orr.ReplayMiss) as e:
        ask(make("replay"))
    assert calls["n"] == 0 and "cache miss" in str(e.value)


def test_record_then_replay_is_free_and_identical(env):
    make, calls = env
    r1 = ask(make("record")).choices[0].message.content
    live_cost = ledger.spent()
    assert calls["n"] == 1 and live_cost == pytest.approx(orr.cost_of("qwen/qwen3.7-flash", 100, 10))
    r2 = ask(make("replay")).choices[0].message.content           # fresh transport, same request
    assert r2 == r1 and calls["n"] == 1 and ledger.spent() == live_cost
    last = ledger.entries()[-1]
    assert last["cached"] and last["cost_usd"] == 0 and last["would_cost_usd"] > 0


def test_repeated_identical_request_gets_own_sample_in_order(env):
    make, calls = env
    c = make("record")
    a, b = ask(c).choices[0].message.content, ask(c).choices[0].message.content
    assert a != b and calls["n"] == 2
    c2 = make("replay")
    assert [ask(c2).choices[0].message.content for _ in range(2)] == [a, b]


def test_salt_separates_runs(env):
    make, calls = env
    ask(make("record", salt="seed1"))
    with pytest.raises(orr.ReplayMiss):
        ask(make("replay", salt="seed2"))


def test_cap_blocks_before_the_call(env, monkeypatch):
    make, calls = env
    monkeypatch.setitem(ledger.CAPS, "p0_ping", 0.0000001)
    with pytest.raises(ledger.CapExceeded) as e:
        ask(make("record"), model="openai/gpt-4o")
    assert calls["n"] == 0 and "cap" in str(e.value)


def test_programme_total_cap(env, monkeypatch):
    make, calls = env
    ledger.record("chimera_minimax", "openai/gpt-4o", 0, 0, 24.99999, cached=False)
    monkeypatch.setitem(ledger.CAPS, "p0_ping", 5.0)
    with pytest.raises(ledger.CapExceeded):
        ask(make("record"), model="openai/gpt-4o")
    assert calls["n"] == 0


def test_halts_are_not_swallowed_by_except_exception():
    """The point of SandboxHalt: upstream's `except Exception` retry loops must not be able to absorb a stop."""
    assert not issubclass(ledger.CapExceeded, Exception) and not issubclass(orr.ReplayMiss, Exception)


def test_unpriced_model_has_no_fallback(env):
    make, calls = env
    with pytest.raises(ledger.SandboxHalt):
        ask(make("record"), model="some/unknown-model")
    assert calls["n"] == 0
    with pytest.raises(KeyError):
        orr.price_of("some/unknown-model")


def test_prices_match_openrouter_list():
    assert orr.price_of("openai/gpt-4o") == (2.5, 10.0)
    assert orr.price_of("qwen/qwen3.7-flash") == (0.03, 0.13)
    assert orr.resolve_model("gpt-4o") == orr.MODEL == "minimax/minimax-m3"
    assert orr.price_of(orr.MODEL) == (0.3, 1.2)


def test_retry_storm_guard_halts_an_identical_request_sent_too_often(env):
    make, calls = env
    c = make("record")
    limit = int(__import__("os").environ.get("SANDBOX_MAX_LIVE_REPEATS", "14"))
    for _ in range(limit):
        ask(c)                                           # `limit` live samples of the same prompt are allowed
    with pytest.raises(ledger.SandboxHalt) as e:
        ask(c)
    assert "retry storm" in str(e.value) and calls["n"] == limit


def test_failed_response_does_not_consume_a_sample_slot(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    state = {"n": 0}

    def handler(request):
        state["n"] += 1
        if state["n"] <= 2:
            return httpx.Response(503, json={"error": "overloaded"})
        return httpx.Response(200, json={"id": "x", "model": "m", "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": "ok"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 2}})
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    t = orr.CachingTransport("p0_ping", "", cache_dir=tmp_path / "c", mode_="record")
    t._inner = httpx.MockTransport(handler)
    from openai import OpenAI
    c = OpenAI(api_key="k", base_url=orr.BASE_URL, http_client=httpx.Client(transport=t), max_retries=3)
    assert ask(c).choices[0].message.content == "ok"      # two 503s retried by the SDK, then success
    assert ledger.spent() > 0 and len(list((tmp_path / "c").glob("*.json"))) == 1
    assert list((tmp_path / "c").glob("*.json"))[0].name.endswith(".0.json")   # stored in slot 0 despite the failed attempts


def test_max_tokens_escalates_for_a_repeatedly_failing_prompt_but_replay_key_is_stable(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    seen = []

    def handler(request):
        seen.append(json.loads(request.content)["max_tokens"])
        return httpx.Response(200, json={"id": "x", "model": "m", "choices": [{"index": 0, "finish_reason": "length",
            "message": {"role": "assistant", "content": ""}}], "usage": {"prompt_tokens": 10, "completion_tokens": seen[-1]}})
    t = orr.CachingTransport("p0_ping", "", cache_dir=tmp_path / "c", mode_="record")
    t._inner = httpx.MockTransport(handler)
    from openai import OpenAI
    c = OpenAI(api_key="k", base_url=orr.BASE_URL, http_client=httpx.Client(transport=t), max_retries=0)
    for _ in range(10):
        c.chat.completions.create(model="qwen/qwen3.7-flash", messages=[{"role": "user", "content": "x"}], max_tokens=1000)
    assert seen == [1000] * 4 + [2000] * 4 + [3000] * 2
    # replay with a fresh transport finds all 10 slots under the ORIGINAL body's key
    r = orr.CachingTransport("p0_ping", "", cache_dir=tmp_path / "c", mode_="replay")
    c2 = OpenAI(api_key="k", base_url=orr.BASE_URL, http_client=httpx.Client(transport=r), max_retries=0)
    for _ in range(10):
        c2.chat.completions.create(model="qwen/qwen3.7-flash", messages=[{"role": "user", "content": "x"}], max_tokens=1000)


def test_hung_request_is_cut_off_by_the_wall_clock_deadline_and_retried(tmp_path, monkeypatch):
    import threading
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("SANDBOX_REQUEST_DEADLINE", "0.5")
    calls = {"n": 0}
    release = threading.Event()

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            release.wait(5)                       # first attempt "hangs" (a provider that stalls but keeps the socket open)
        return httpx.Response(200, json={"id": "x", "model": "m", "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": "ok"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 2}})
    t = orr.CachingTransport("p0_ping", "", cache_dir=tmp_path / "c", mode_="record")
    t._inner = httpx.MockTransport(handler)
    from openai import OpenAI
    c = OpenAI(api_key="k", base_url=orr.BASE_URL, http_client=httpx.Client(transport=t), max_retries=2)
    import time
    t0 = time.time()
    assert ask(c).choices[0].message.content == "ok"
    assert calls["n"] == 2 and time.time() - t0 < 4          # hung attempt abandoned at 0.5 s, retry succeeded
    release.set()


def test_attempt_that_got_no_response_is_replayed_as_the_same_failure(tmp_path, monkeypatch):
    """A recorded attempt cut off by the deadline uses its slot but saves nothing; the client's retry lands in the next slot.
    Replay must reproduce that failure (so the client retries the same way), not miss the cache or fetch a new sample."""
    import threading
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("SANDBOX_REQUEST_DEADLINE", "0.5")
    calls = {"n": 0}
    release = threading.Event()

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            release.wait(5)
        return httpx.Response(200, json={"id": "x", "model": "m", "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": f"r{calls['n']}"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 2}})
    from openai import OpenAI
    t = orr.CachingTransport("p0_ping", "", cache_dir=tmp_path / "c", mode_="record")
    t._inner = httpx.MockTransport(handler)
    assert ask(OpenAI(api_key="k", base_url=orr.BASE_URL, http_client=httpx.Client(transport=t), max_retries=2)).choices[0].message.content == "r2"
    release.set()
    assert sorted(p.name.split(".")[1] for p in (tmp_path / "c").glob("*.json")) == ["1"]      # slot 0 is a hole

    r = orr.CachingTransport("p0_ping", "", cache_dir=tmp_path / "c", mode_="replay")
    c = OpenAI(api_key="k", base_url=orr.BASE_URL, http_client=httpx.Client(transport=r), max_retries=2)
    assert ask(c).choices[0].message.content == "r2" and calls["n"] == 2
    with pytest.raises(orr.ReplayMiss):                    # a missing slot with nothing after it is still a hard miss
        ask(c)
