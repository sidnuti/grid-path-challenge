"""Programme ledger: `sandbox_scenarios/ledger.jsonl`, per-item sub-caps (all paid items $0 until approved).

Append-only JSONL, one line per LLM call (live or cache hit). Spend is always *re-priced from tokens*
(never trusted from a provider field), following `experiments/x8_l2prime/x8_run.py::spent()`.
`check()` runs BEFORE every live call and raises `CapExceeded`; a cache hit costs $0 and is logged
with `cached: true` so a replay can be audited as free.

    python -m common.ledger --summary
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # .../sandbox_scenarios
LEDGER_PATH = Path(os.environ.get("SANDBOX_LEDGER", ROOT / "ledger.jsonl"))

TOTAL_CAP = 0.05                          # sandbox_scenarios: no paid budget approved yet; raised only on explicit user approval
CAPS = {                                  # plan/2026-10-05_sandbox_ads_e2e_plan.md, P5: caps set from the pilot
    "p0_ping": 0.05,                      # connectivity check only
    "ads_pilot": 0.0,                     # P5.1 pilot: needs user approval
    "ads_e1": 0.0,
    "ads_e2": 0.0,
    "ads_e3": 0.0,
}


class SandboxHalt(BaseException):
    """Stop conditions (cap hit, replay miss, unpriced model). Deliberately a BaseException: upstream code wraps LLM calls in
    `except Exception` (MoHOLLM's `while True ... except Exception: retry`, Chimera's per-week `except Exception: no-op`), which
    would swallow an ordinary exception and either spin forever or silently finish a run full of no-op actions."""


class CapExceeded(SandboxHalt):
    pass


def entries(path: Path | None = None) -> list[dict]:
    path = path or LEDGER_PATH
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def spent(item: str | None = None, path: Path | None = None) -> float:
    return sum(e["cost_usd"] for e in entries(path) if item is None or e["item"] == item)


def check(item: str, projected_usd: float, path: Path | None = None) -> None:
    """Refuse the call if it could push `item` or the programme over its cap."""
    if item not in CAPS:
        raise CapExceeded(f"unknown ledger item {item!r}; known: {sorted(CAPS)}")
    es = entries(path)
    item_spent = sum(e["cost_usd"] for e in es if e["item"] == item)
    total_spent = sum(e["cost_usd"] for e in es)
    if item_spent + projected_usd > CAPS[item]:
        raise CapExceeded(f"{item}: spent ${item_spent:.4f} + projected ${projected_usd:.4f} > cap ${CAPS[item]:.2f}")
    if total_spent + projected_usd > TOTAL_CAP:
        raise CapExceeded(f"programme: spent ${total_spent:.4f} + projected ${projected_usd:.4f} > cap ${TOTAL_CAP:.2f}")


def record(item: str, model: str, tokens_in: int, tokens_out: int, cost_usd: float, *, cached: bool,
           key: str = "", note: str = "", provider_cost_usd: float | None = None, path: Path | None = None) -> dict:
    e = {"ts": round(time.time(), 3), "item": item, "model": model, "tokens_in": tokens_in,
         "tokens_out": tokens_out, "cost_usd": 0.0 if cached else round(cost_usd, 8), "cached": cached,
         "key": key[:16], "note": note}
    if cached:
        e["would_cost_usd"] = round(cost_usd, 8)
    if provider_cost_usd is not None:
        e["provider_cost_usd"] = provider_cost_usd
    path = path or LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(e) + "\n")
    return e


def summary(path: Path | None = None) -> str:
    path = path or LEDGER_PATH
    es = entries(path)
    lines = [f"ledger: {path}  ({len(es)} entries)", f"{'item':<16}{'live calls':>11}{'cached':>8}{'spent $':>10}{'cap $':>8}"]
    for item, cap in CAPS.items():
        sub = [e for e in es if e["item"] == item]
        lines.append(f"{item:<16}{sum(not e['cached'] for e in sub):>11}{sum(e['cached'] for e in sub):>8}"
                     f"{sum(e['cost_usd'] for e in sub):>10.4f}{cap:>8.2f}")
    lines.append(f"{'TOTAL':<16}{'':>11}{'':>8}{spent(path=path):>10.4f}{TOTAL_CAP:>8.2f}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary())
