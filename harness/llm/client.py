"""The provider-agnostic contract every leaf (`harness/leaves/run.py`) calls through. Nothing
above this layer knows which provider is live, what `LLM_MODE` is, or whether a fault is being
injected — that is `providers.py`/`replay.py`/`faults.py`'s job to assemble into one `LLMClient`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Usage:
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    wall_clock_s: float = 0.0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.calls + other.calls, self.tokens_in + other.tokens_in,
                     self.tokens_out + other.tokens_out, self.cost_usd + other.cost_usd,
                     self.wall_clock_s + other.wall_clock_s)


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str, schema: dict, timeout: float) -> tuple[dict, Usage]:
        """Returns (parsed JSON object matching `schema` as best the provider can manage, Usage).
        Raises on a hard failure (timeout, malformed response after the one repair retry,
        provider error) — callers (`harness/leaves/run.py`) catch and fall back to the leaf's
        default; this protocol does not swallow errors itself."""
        ...
