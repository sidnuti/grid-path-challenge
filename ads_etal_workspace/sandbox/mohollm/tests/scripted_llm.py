"""Deterministic stand-in for the LLM: answers surrogate prompts with a cheap, smooth fake objective of the parsed candidates
and refuses everything else. Lets the real optimisation loop run offline."""
import ast
import json
import re

from mohollm.llm.llm import LLMInterface


def fake_objective(cfg: dict) -> dict:
    v = [float(x) for x in cfg.values()]
    return {"F1": round(sum((x - 0.3) ** 2 for x in v), 4), "F2": round(sum((x - 0.7) ** 2 for x in v), 4)}


class ScriptedSurrogateLLM(LLMInterface):
    def __init__(self):
        super().__init__()
        self.calls = []

    def prompt(self, prompt: str, max_number_of_tokens=100, **kwargs) -> str:
        self.calls.append(prompt)
        block = prompt.split("## Candidate configurations to Evaluate")[1].split("## Your Task")[0]
        cands = [ast.literal_eval(m) for m in re.findall(r"^\d+: (\{.*\})$", block, re.M)]
        assert cands, "no candidates parsed from surrogate prompt"
        return "```json\n" + json.dumps([fake_objective(c) for c in cands]) + "\n```"

    def update_cost_and_token_usage(self, response):
        pass
