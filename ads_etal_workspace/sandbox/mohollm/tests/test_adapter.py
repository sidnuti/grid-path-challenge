"""adapters/ledger_hook.py: MoHOLLM's OpenRouter model class is routed through the sandbox cache/ledger."""
import json
from pathlib import Path

import pytest

from adapters import ledger_hook
from common import ledger, openrouter as orr

pytestmark = pytest.mark.offline
UP = Path(__file__).resolve().parents[1] / "upstream"


def test_install_registers_models_and_routes_client(monkeypatch, tmp_path):
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "l.jsonl")
    monkeypatch.setattr(orr, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setenv("SANDBOX_LLM_MODE", "replay")
    ledger_hook.install("mohollm_minimax", salt="t")
    from mohollm.llm.models.openrouter import OPENROUTER
    from mohollm.settings import MODELS
    from mohollm.utils.rate_limiter import RateLimiter
    assert MODELS[orr.MODEL] is OPENROUTER
    m = OPENROUTER(orr.MODEL)
    assert str(m.client.base_url).startswith(orr.BASE_URL)
    m.rate_limiter = RateLimiter(max_tokens=10_000, time_frame=60, max_requests=100)
    m.llm_settings = {}
    with pytest.raises(orr.ReplayMiss):                 # nothing recorded -> hard stop, never a live call
        m.prompt("hello")
    assert ledger.entries() == []


def test_overlay_swaps_model_and_prices_without_touching_original():
    base = json.load(open(UP / "configurations/Simple2D/mohollm-BraninCurrin.json"))
    c = ledger_hook.overlay(base, "gemini-2.0-flash")           # paper model name -> minimax-m3
    assert c["llm_settings"]["model"] == orr.MODEL
    assert c["llm_settings"]["input_cost_per_1000_tokens"] == pytest.approx(0.30 / 1000)
    assert c["llm_settings"]["output_cost_per_1000_tokens"] == pytest.approx(1.20 / 1000)
    assert base["llm_settings"]["model"] == "gemini-2.0-flash"  # deep copy
    assert c["benchmark"] == base["benchmark"] and c["n_trials"] == base["n_trials"]


def test_recorded_response_is_served_through_upstream_class(monkeypatch, tmp_path):
    """Full path with a recorded cache entry: upstream OPENROUTER.prompt -> transport -> cache hit, $0, ledgered as cached."""
    import hashlib

    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "l.jsonl")
    monkeypatch.setattr(orr, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setenv("SANDBOX_LLM_MODE", "replay")
    ledger_hook.install("mohollm_minimax", salt="t")
    from mohollm.llm.models.openrouter import OPENROUTER
    from mohollm.statistics.statistics import Statistics
    from mohollm.utils.rate_limiter import RateLimiter
    m = OPENROUTER(orr.MODEL)
    m.rate_limiter = RateLimiter(max_tokens=10_000, time_frame=60, max_requests=100)
    m.llm_settings, m.statistics = {"max_number_of_tokens": 50, "temperature": 0.2}, Statistics()
    body = {"model": orr.MODEL, "messages": [{"role": "system", "content": "You are an AI assistant that helps people find information."},
                                              {"role": "user", "content": "ping"}], "max_tokens": 50, "temperature": 0.2, "n": 1}
    key = hashlib.sha256(("t" + "\0" + json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)).encode()).hexdigest() + ".0"
    d = tmp_path / "cache" / "mohollm_minimax"
    d.mkdir(parents=True)
    (d / f"{key}.json").write_text(json.dumps({"response": {"id": "x", "object": "chat.completion", "created": 0, "model": orr.MODEL,
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "pong"}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23}}}))
    assert m.prompt("ping") == "pong"
    e = ledger.entries()[-1]
    assert e["cached"] and e["cost_usd"] == 0 and e["item"] == "mohollm_minimax"


def test_shuffles_are_content_seeded_and_thread_independent(monkeypatch, tmp_path):
    """Regression for the replay bug: prompt row order must not depend on the global RNG / thread scheduling."""
    import random
    import threading

    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "l.jsonl")
    ledger_hook.install("mohollm_minimax", salt="t")
    from mohollm.utils.prompt_builder import PromptBuilder
    pb = PromptBuilder.__new__(PromptBuilder)
    rows = [f"row {i}" for i in range(12)]
    base = pb._shuffle_config_rows(list(rows))
    assert base != rows and sorted(base) == sorted(rows)
    out = []

    def work():
        for _ in range(50):
            random.random()                                   # churn the global RNG from many threads
        out.append(pb._shuffle_config_rows(list(rows)))
    ts = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert all(o == base for o in out)
    random.seed(1)
    assert pb._shuffle_config_rows(list(rows)) == base
    cfg = {"x0": 1, "x1": 2, "x2": 3, "x3": 4}
    assert list(pb._shuffle_config_columns(cfg)) == list(pb._shuffle_config_columns(cfg))


def test_tabpfn_surrogate_is_pinned_to_v2_and_predicts(tmp_path, monkeypatch):
    """Uses the cached v2 weights (downloaded once; open, no license step). Predictions are deterministic."""
    import numpy as np
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "l.jsonl")
    ledger_hook.install("mohollm_minimax", salt="t")
    import mohollm.surrogate_models.tabpfn as tp
    m1 = tp.TabPFNRegressor()
    rng = np.random.default_rng(0)
    X, Xq = rng.random((25, 7)), rng.random((4, 7))
    y = X.sum(1)
    p1 = m1.fit(X, y).predict(Xq)
    p2 = tp.TabPFNRegressor().fit(X, y).predict(Xq)
    np.testing.assert_allclose(p1, p2, atol=1e-5)
    assert np.corrcoef(p1, Xq.sum(1))[0, 1] > 0.9          # it actually learned the sum
    cache = __import__("pathlib").Path.home() / "Library" / "Caches" / "tabpfn"
    names = [f.name for f in cache.glob("*.ckpt")]
    assert "tabpfn-v2-regressor.ckpt" in names and not any("v3" in n or "v2.5" in n or "v2.6" in n for n in names), names
