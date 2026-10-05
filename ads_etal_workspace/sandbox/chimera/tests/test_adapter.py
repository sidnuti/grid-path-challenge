"""adapters/llm.py: upstream's `ChatOpenAI(model="gpt-4o", ...)` becomes an OpenRouter call through the cache/ledger."""
import json

import httpx
import pytest

from common import ledger, openrouter as orr

pytestmark = pytest.mark.offline


def test_install_reroutes_chat_openai(monkeypatch):
    import preprint.three_agent_comparative_benchmark as b
    from adapters import llm
    llm.install(b, item="chimera_minimax", salt="t")
    m = b.ChatOpenAI(model="gpt-4o", temperature=0.9, max_tokens=1000, openai_api_key="sk-should-be-ignored")
    assert m.model_name == orr.MODEL == "minimax/minimax-m3"
    assert m.openai_api_base == orr.BASE_URL
    assert m.max_tokens == llm.MIN_MAX_TOKENS          # reasoning model: 1000 would be eaten by thinking tokens
    assert m.temperature == 0.9
    assert "sk-should-be-ignored" not in repr(m.openai_api_key)


def test_replay_miss_never_reaches_network(monkeypatch, tmp_path):
    from adapters import llm
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "l.jsonl")
    monkeypatch.setenv("SANDBOX_LLM_MODE", "replay")
    monkeypatch.setattr(orr, "CACHE_ROOT", tmp_path / "cache")
    m = llm.make_chat_llm("gpt-4o", 0.0, item="chimera_minimax", salt="nope", max_tokens=100)
    with pytest.raises(orr.ReplayMiss):
        m.invoke("hello")
    assert ledger.entries() == []
