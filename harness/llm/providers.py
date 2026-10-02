"""Three thin provider adapters behind the same `LLMClient.complete_json` contract. Imports of
`openai`/`anthropic` are lazy (inside `__init__`), so importing this module never requires either
package to be installed unless the corresponding provider is actually selected.

Newer Claude models (per the open item raised for Gobblecube) no longer accept a `temperature`
parameter — none of these adapters sets one; provider defaults apply.

JSON enforcement: all three ask for JSON-only via the provider's native structured-output
mechanism where available (OpenAI/OpenRouter `response_format`), and fall back to a strict
system-prompt instruction + one repair retry (re-send with the parse error) everywhere, since not
every OpenRouter-routed model supports `response_format`.
"""

from __future__ import annotations

import json
import os
import time

from .client import Usage

_JSON_ONLY = ("Respond with a single JSON object only — no prose, no markdown fences, no "
              "explanation before or after. The object must validate against this JSON schema:\n{schema}")
_REPAIR = ("Your previous response could not be parsed as JSON matching the schema. "
           "Error: {error}\nRespond again with a single valid JSON object only.")


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


class OpenAICompatClient:
    """Shared implementation for OpenAI and OpenRouter — both speak the `openai` SDK's chat
    completions API; OpenRouter is just a different `base_url`."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        import openai  # lazy
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def complete_json(self, system: str, user: str, schema: dict, timeout: float, **_ignored) -> tuple[dict, Usage]:
        t0 = time.monotonic()
        messages = [{"role": "system", "content": system + "\n\n" + _JSON_ONLY.format(schema=json.dumps(schema))},
                    {"role": "user", "content": user}]
        usage = Usage()
        for attempt in range(2):
            resp = self._client.chat.completions.create(model=self.model, messages=messages, timeout=timeout)
            u = getattr(resp, "usage", None)
            if u is not None:
                usage.calls += 1
                usage.tokens_in += getattr(u, "prompt_tokens", 0) or 0
                usage.tokens_out += getattr(u, "completion_tokens", 0) or 0
            text = resp.choices[0].message.content or ""
            try:
                parsed = _extract_json(text)
                usage.wall_clock_s += time.monotonic() - t0
                return parsed, usage
            except (json.JSONDecodeError, ValueError) as e:
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": _REPAIR.format(error=str(e))})
        usage.wall_clock_s += time.monotonic() - t0
        raise ValueError(f"{self.model}: no valid JSON after one repair retry")


class OpenRouterClient(OpenAICompatClient):
    def __init__(self, model: str, api_key: str | None = None):
        super().__init__(api_key=api_key or os.environ["OPENROUTER_API_KEY"], model=model,
                         base_url="https://openrouter.ai/api/v1")


class OpenAIClient(OpenAICompatClient):
    def __init__(self, model: str, api_key: str | None = None):
        super().__init__(api_key=api_key or os.environ["OPENAI_API_KEY"], model=model)


class AnthropicClient:
    def __init__(self, model: str, api_key: str | None = None):
        import anthropic  # lazy
        self._client = anthropic.Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
        self.model = model

    def complete_json(self, system: str, user: str, schema: dict, timeout: float, **_ignored) -> tuple[dict, Usage]:
        t0 = time.monotonic()
        sys_prompt = system + "\n\n" + _JSON_ONLY.format(schema=json.dumps(schema))
        messages = [{"role": "user", "content": user}]
        usage = Usage()
        for attempt in range(2):
            resp = self._client.messages.create(model=self.model, max_tokens=2048, system=sys_prompt,
                                                 messages=messages, timeout=timeout)
            u = getattr(resp, "usage", None)
            if u is not None:
                usage.calls += 1
                usage.tokens_in += getattr(u, "input_tokens", 0) or 0
                usage.tokens_out += getattr(u, "output_tokens", 0) or 0
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            try:
                parsed = _extract_json(text)
                usage.wall_clock_s += time.monotonic() - t0
                return parsed, usage
            except (json.JSONDecodeError, ValueError) as e:
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": _REPAIR.format(error=str(e))})
        usage.wall_clock_s += time.monotonic() - t0
        raise ValueError(f"{self.model}: no valid JSON after one repair retry")


DEFAULT_MODEL = "anthropic/claude-sonnet-5"


def build_provider(provider: str | None = None, model: str | None = None):
    """`provider` defaults to `LLM_PROVIDER` ("openrouter" if unset); `model` to `LLM_MODEL` or
    `DEFAULT_MODEL`. Returns None for provider "none" (tools-only, no client needed)."""
    provider = provider or os.environ.get("LLM_PROVIDER", "openrouter")
    model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    if provider == "none":
        return None
    if provider == "openrouter":
        return OpenRouterClient(model=model)
    if provider == "openai":
        return OpenAIClient(model=model)
    if provider == "anthropic":
        return AnthropicClient(model=model)
    raise ValueError(f"unknown LLM_PROVIDER: {provider}")
