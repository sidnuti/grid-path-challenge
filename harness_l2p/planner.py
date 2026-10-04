"""LLM planner for L2′: brief in, `IntentPlan` out, through the harness's existing leaf call path
(`harness.leaves.run.leaf` → ReplayClient → Meter → faults → provider). One plan call per run and
at most one repair call that sees the compiler's rejections. Any failure returns the empty plan
with `meta.outcome == "default"`; the policy decides what that means (augment → L0, native → L0
on error, nothing on a legitimate empty plan).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from harness.leaves.run import leaf

from .brief import Brief
from .intents import EMPTY_PLAN, IntentPlan

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_VERSION = "2"   # v2 (2026-10-04): value of unspent room, iROAS over dROAS, protected cells


@lru_cache(maxsize=None)
def _load(name: str, version: str) -> tuple[str, str]:
    text = (PROMPTS_DIR / f"{name}.v{version}.md").read_text()
    _, _, rest = text.partition("<!-- system -->")
    system, _, user = rest.partition("<!-- user -->")
    return system.strip(), user.strip()


def _known(brief: Brief) -> dict:
    return {"brief_refs": len(brief.refs)}


def plan_with_llm(llm, brief: Brief, feedback: str = "", replicate: int = 0, leaf_name: str = "L2P_plan",
                  timeout: float = 300.0) -> tuple[IntentPlan, dict]:
    system, tmpl = _load("L2P_plan", PROMPT_VERSION)
    user = tmpl.format(brief=brief.text, feedback=feedback)
    # the reasoning setting changes the answer, so it is part of the replay cache key (via prompt_ver)
    ver = f"{PROMPT_VERSION}-r{os.environ.get('L2P_REASONING', 'on')}"
    plan, meta = leaf(llm, leaf_name, system, user, IntentPlan, EMPTY_PLAN, timeout=timeout,
                      prompt_ver=ver, replicate=replicate)
    meta["prompt_chars"] = len(system) + len(user)
    meta["n_intents"] = len(plan.intents)
    return plan, meta


def repair_feedback(rejected: list[dict], max_lines: int = 25) -> str:
    if not rejected:
        return ""
    lines = [f"- intent {r.get('intent_id', '?')}{' ' + r['cell'] if r.get('cell') else ''}: {r['reason']}"
             for r in rejected[:max_lines]]
    return ("Your previous plan for this run had intents the compiler rejected:\n" + "\n".join(lines) +
            "\nReturn a revised full plan that keeps what worked and fixes or drops what was rejected.\n")
