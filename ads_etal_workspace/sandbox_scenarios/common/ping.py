"""Gate-P0 ping: one tiny completion per model, written to the ledger. Run twice: record, then replay ($0).

    SANDBOX_LLM_MODE=record python -m common.ping      # live, <= $0.01 total
    SANDBOX_LLM_MODE=replay python -m common.ping      # must cost $0
"""
from __future__ import annotations

import sys

from . import ledger, openrouter as orr

MODELS = [orr.MODEL]
PROMPT = "Reply with the single word: pong"

if __name__ == "__main__":
    before = ledger.spent("p0_ping")
    for m in MODELS:
        text, tin, tout = orr.chat("p0_ping", m, PROMPT, max_tokens=1024)
        print(f"{m:<32} {tin:>3} in {tout:>3} out  cost ${orr.cost_of(m, tin, tout):.6f}  -> {text!r}")
    print(f"mode={orr.mode()}  ledger delta this run: ${ledger.spent('p0_ping') - before:.6f}")
