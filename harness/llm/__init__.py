"""`build_llm_stack(params)`: assembles provider -> fault-injection -> meter -> replay into the
one `ReplayClient` a leaf talks to, reading `.env` (via `python-dotenv`, loaded once here) and
the `LLM_*` environment variables documented in `.env.example`. `LLM_MODE=off` (the default)
returns a client whose `complete_json` is never reached — callers should check `mode == "off"`
and skip straight to the leaf default, which `harness/leaves/run.py` does by receiving `llm=None`
in that case rather than a no-op client, so there is exactly one no-LLM code path, not two.
"""

from __future__ import annotations

import os

from ..config import Params
from .client import LLMClient
from .faults import FaultInjectingClient
from .meter import Meter, reset_run_budget  # noqa: F401 - re-exported for harness/policy.py
from .providers import build_provider
from .replay import ReplayClient

_dotenv_loaded = False


def _load_dotenv_once() -> None:
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    _dotenv_loaded = True


def build_llm_stack(params: Params) -> tuple[LLMClient | None, str]:
    """Returns (client_or_None, mode). `client` is None iff `mode == "off"` or `LLM_PROVIDER ==
    "none"` — both mean "tools-only this call", handled by `leaf()` receiving `llm=None`."""
    _load_dotenv_once()
    mode = os.environ.get("LLM_MODE", "off")
    if mode == "off":
        return None, mode
    provider_name = os.environ.get("LLM_PROVIDER", "openrouter")
    model = os.environ.get("LLM_MODEL")
    provider = build_provider(provider_name, model)
    if provider is None:
        return None, mode
    faulted = FaultInjectingClient(provider, os.environ.get("FAULT_INJECT", ""))
    metered = Meter(faulted, model or "", params.llm_max_usd_per_run)
    cache_dir = os.environ.get("LLM_CACHE_DIR", "llm_cache")
    return ReplayClient(metered, cache_dir, mode), mode
