"""Build Chimera's chat models through OpenRouter + the sandbox cache/ledger, without editing upstream.

Upstream constructs `ChatOpenAI(model="gpt-4o", temperature=0.9, max_tokens=1000, openai_api_key=...)` inline in
each agent factory. `install(module, ...)` swaps the `ChatOpenAI` name in that module for `RoutedChatOpenAI`,
which ignores the key, points at OpenRouter, and uses `common.openrouter.CachingTransport`:

    import preprint.three_agent_comparative_benchmark as b
    llm.install(b, item="chimera_minimax", salt="seed0")                       # paper model name is aliased to minimax-m3
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))          # sandbox/
from common import openrouter as orr                                  # noqa: E402

from langchain_openai import ChatOpenAI                               # noqa: E402


MIN_MAX_TOKENS = 8000   # upstream hard-codes max_tokens=1000; minimax-m3 is a reasoning model whose thinking
                        # tokens count against it, so 1000 can truncate before the JSON answer is emitted.


def make_chat_llm(model: str, temperature: float = 0.0, *, item: str, salt: str = "", max_tokens: int | None = None,
                  **kw) -> ChatOpenAI:
    max_tokens = max(max_tokens or 0, MIN_MAX_TOKENS) if max_tokens is not None else None
    return ChatOpenAI(model=orr.resolve_model(model), temperature=temperature, max_tokens=max_tokens,
                      api_key=orr.api_key() if orr.mode() != "replay" else "replay-no-key",
                      base_url=orr.BASE_URL, http_client=orr.http_client(item, salt), max_retries=3,
                      disable_streaming=True, **kw)   # AgentExecutor streams; the transport is non-streaming


def install(module, *, item: str, salt: str = "", model: str | None = None) -> None:
    """Replace `module.ChatOpenAI` with a router bound to (item, salt[, model override])."""

    def routed(*args, **kw):
        kw.pop("openai_api_key", None)
        kw.pop("api_key", None)
        m = model or kw.pop("model", None) or kw.pop("model_name", None) or "gpt-4o"
        kw.pop("model", None)
        return make_chat_llm(m, kw.pop("temperature", 0.0), item=item, salt=salt, max_tokens=kw.pop("max_tokens", None), **kw)

    module.ChatOpenAI = routed
