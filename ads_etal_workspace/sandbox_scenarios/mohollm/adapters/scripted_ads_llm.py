"""Deterministic offline stand-in for the LLM on GridMarketBenchmark prompts (plan P3: e2e at $0).

  - candidate-sampler prompts ("Generate N new configurations"): N points drawn uniformly inside the stated bounds
    (partitioned: `name: range(float([lo, hi]))`; global: `'name': [lo, hi]`), seeded by the prompt text;
  - surrogate prompts ("Candidate configurations to Evaluate"): a smooth proxy per metric named in the output format.
Anything else is refused. Records every prompt in `calls` so tests can inspect them.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re

import numpy as np

from mohollm.llm.llm import LLMInterface

_RANGE = re.compile(r"(\w+): range\(float\(\[([-\d.eE]+), ([-\d.eE]+)\]\)\)")
_LIST = re.compile(r"'(\w+)': \[([-\d.eE]+), ([-\d.eE]+)\]")


def proxy(cfg: dict, metric: str) -> float:
    v = np.array([float(x) for x in cfg.values()])
    target = {"F1": 0.35, "F2": 0.6, "F3": 0.8}.get(metric, 0.5)
    return round(float(((v - target) ** 2).sum()), 4)


class ScriptedAdsLLM(LLMInterface):
    def __init__(self):
        super().__init__()
        self.calls: list[str] = []

    def prompt(self, prompt: str, max_number_of_tokens=100, **kwargs) -> str:
        self.calls.append(prompt)
        rng = np.random.default_rng(int(hashlib.sha256(prompt.encode()).hexdigest()[:12], 16))
        if "Candidate configurations to Evaluate" in prompt:
            block = prompt.split("## Candidate configurations to Evaluate")[1].split("## Your Task")[0]
            cands = [ast.literal_eval(m) for m in re.findall(r"^\d+: (\{.*\})$", block, re.M)]
            assert cands, "no candidates parsed from surrogate prompt"
            fmt = prompt.split("## Output Format")[1]
            metrics = sorted(set(re.findall(r'"(F\d)"', fmt)))
            return "```json\n" + json.dumps([{m: proxy(c, m) for m in metrics} for c in cands]) + "\n```"
        m = re.search(r"Generate (\d+) new configurations", prompt)
        if m:
            n = int(m.group(1))
            section = prompt.split("## Constraints")[1].split("## Previously")[0]
            bounds = _RANGE.findall(section) or _LIST.findall(section)
            assert bounds, "no bounds parsed from candidate-sampler prompt"
            pts = [{k: round(float(rng.uniform(float(lo), float(hi))), 4) for k, lo, hi in bounds} for _ in range(n)]
            return "```json\n" + json.dumps(pts) + "\n```"
        raise AssertionError("scripted LLM: unexpected prompt kind")

    def update_cost_and_token_usage(self, response):
        pass
