"""Writes one `RunTrace` per run as a JSONL line. Off by default, per the plan ("default off
during `make score`") — controlled entirely by the `TRACE_DIR` env var: unset or empty means no
file is ever opened, which is also what keeps this out of the AST rule scan's "no file opens"
concern (there's nothing conditional-on-content here; it is conditional on an env var the user
sets, same as `LLM_MODE`).

    TRACE_DIR=traces python -m gpc.runner --policy harness.policy:HTNHarness

writes `traces/<policy_name>.jsonl`, one line per run, appended (not truncated) so a multi-run
`simulate()` call builds one file across all its runs.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from gpc.observation import Observation

from .schema import RunTrace, build_trace


def trace_dir() -> Path | None:
    d = os.environ.get("TRACE_DIR", "")
    return Path(d) if d else None


def maybe_write_trace(policy_name: str, simulation_id: str, obs: Observation, params, llm, actions: pd.DataFrame,
                      run_trace: dict) -> RunTrace | None:
    """No-op (returns None, writes nothing) when `TRACE_DIR` is unset. Otherwise builds and
    appends a `RunTrace` and returns it (useful for tests, which can assert on the returned
    object without re-reading the file). `simulation_id` (one per policy instance, i.e. one per
    `simulate()` call) lets a reader group rows from the same file back into simulations."""
    d = trace_dir()
    if d is None:
        return None
    trace = build_trace(policy_name, simulation_id, obs, params, llm, actions, run_trace)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{policy_name}.jsonl"
    with path.open("a") as f:
        f.write(json.dumps(asdict(trace), default=str) + "\n")
    return trace


def read_traces(path: str | Path) -> list[RunTrace]:
    """Reads a `.jsonl` file written by `maybe_write_trace` back into `RunTrace` objects —
    for `harness/s2/learner_stub.py` and tests, not used by the harness itself at decision time."""
    out = []
    with Path(path).open() as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(RunTrace(**json.loads(line)))
    return out
