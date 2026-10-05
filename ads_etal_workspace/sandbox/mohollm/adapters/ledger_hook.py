"""Route MoHOLLM's LLM traffic through OpenRouter + the sandbox cache/ledger, without editing upstream.

Upstream's `OPENROUTER` model class already speaks OpenAI-compatible chat completions to OpenRouter,
and `MODELS` (a plain dict in `mohollm.settings`) maps a model name to a class. So at runtime we:

  1. register every OpenRouter model id we use in `MODELS` -> `OPENROUTER`;
  2. replace the `OpenAI` constructor inside `mohollm.llm.models.openrouter` with a factory whose HTTP
     transport is `common.openrouter.CachingTransport` (cache + ledger + cap, one place for all money).

This replaces the plan's "wrap `update_cost_and_token_usage`": hooking the transport also covers
failed/ retried calls and does not depend on upstream's per-config price fields (which we overwrite
anyway, see `overlay`). Upstream's own `statistics` cost stays for per-run reporting.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))          # sandbox/
from common import openrouter as orr                                  # noqa: E402

UPSTREAM = Path(__file__).resolve().parents[1] / "upstream"

_state = {"item": None, "salt": ""}


def install(item: str, salt: str = "") -> None:
    """Idempotent. `item` is the ledger line (e.g. 'mohollm_minimax'); `salt` the run tag (seed etc.)."""
    if str(UPSTREAM) not in sys.path:
        sys.path.insert(0, str(UPSTREAM))
    import mohollm.llm.models.openrouter as om
    from mohollm import settings
    from mohollm.llm.models.openrouter import OPENROUTER

    _state.update(item=item, salt=salt)
    for model in orr.PRICES:
        settings.MODELS[model] = OPENROUTER

    def factory(api_key=None, base_url=None, **kw):
        return orr.openai_client(_state["item"], _state["salt"])

    om.OpenAI = factory
    _patch_shuffles()
    _pin_tabpfn_v2()


def replay_schedule(recorded_run: Path) -> None:
    """Replay a recorded partitioned run under its recorded thread schedule.

    `SpacePartitioning.optimize` runs one thread per region and collects their results with `as_completed`, i.e. in
    completion order; `select_candidate_point` breaks hypervolume ties by position, so which candidate gets evaluated
    depends on thread timing, and a replay (instant cached responses, different timing) diverges after a few trials.
    The schedule is not lost: upstream writes each trial's concatenated candidate list (`llm_candidate_proposal`) to
    `icl_llm_proposal_trajectory/*.csv`. Here `reorganize_data` puts the per-region results back in that recorded order
    (it is a permutation of <= 5 regions) before concatenating. Record mode is unchanged."""
    import ast
    import csv
    import itertools
    import os

    from mohollm.optimization_strategy.space_partitioning_mohollm import SpacePartitioningmohollm as SP

    csv.field_size_limit(1 << 30)
    paths = [os.path.join(p, f) for p, _, fs in os.walk(recorded_run / "results")       # os.walk: dir names contain "[model]"
             if p.endswith("icl_llm_proposal_trajectory") for f in fs]
    if len(paths) != 1:
        raise orr.ReplayMiss(f"replay_schedule: expected one recorded trajectory under {recorded_run}, found {len(paths)}")
    recorded = [ast.literal_eval(r["llm_candidate_proposal"]) for r in csv.DictReader(open(paths[0]))]

    def norm(configs):
        return [tuple(sorted((k, round(float(v), 9)) for k, v in c.items())) for c in configs]

    original = SP.reorganize_data
    state = {"trial": 0}

    def reorganize_data(self, data):
        t = state["trial"]
        state["trial"] += 1
        if t >= len(recorded):
            raise orr.ReplayMiss(f"replay_schedule: trial {t} beyond the {len(recorded)} recorded trials")
        want = norm(recorded[t])
        for perm in itertools.permutations(data):
            if norm([c for configs, _ in perm for c in configs]) == want:
                return original(self, list(perm))
        raise orr.ReplayMiss(f"replay_schedule: no ordering of the {len(data)} region results matches recorded trial {t}")

    SP.reorganize_data = reorganize_data


def _pin_tabpfn_v2() -> None:
    """Upstream calls `TabPFNRegressor()`; the installed tabpfn (9.x) now defaults to the license-gated v3.5, whereas the paper
    used TabPFN-v2 (open weights, ~42 MB, cached under ~/Library/Caches/tabpfn). Pin v2 and CPU (deterministic, no GPU here)."""
    import mohollm.surrogate_models.tabpfn as tp
    from tabpfn import TabPFNRegressor
    from tabpfn.model_loading import ModelVersion

    def v2(*a, **kw):
        return TabPFNRegressor.create_default_for_version(ModelVersion.V2, device="cpu", random_state=0)

    tp.TabPFNRegressor = v2


def _patch_shuffles() -> None:
    """Upstream shuffles ICL rows/columns with the *global* `random`, which the partitioned method's 5 worker threads share,
    so prompt order (hence the cache key) depends on thread scheduling and a recorded run can never be replayed.
    Replace with a shuffle seeded from the items themselves: still a random-looking permutation, independent of thread timing."""
    import hashlib
    import random

    from mohollm.utils.prompt_builder import PromptBuilder

    def _rng(items):
        h = hashlib.sha256("\0".join(map(str, items)).encode()).digest()
        return random.Random(int.from_bytes(h[:8], "big"))

    def rows(self, config: list) -> list:
        config = list(config)
        _rng(config).shuffle(config)
        return config

    def cols(self, config: dict) -> dict:
        items = list(config.items())
        _rng([k for k, _ in items]).shuffle(items)
        return dict(items)

    PromptBuilder._shuffle_config_rows = rows
    PromptBuilder._shuffle_config_columns = cols


def overlay(config: dict, model: str) -> dict:
    """Return a copy of an upstream config JSON with the LLM swapped to an OpenRouter model id and the
    per-1k-token prices set to the true OpenRouter rates (upstream's report fields only)."""
    model = orr.resolve_model(model)
    pin, pout = orr.price_of(model)
    c = copy.deepcopy(config)
    s = c.setdefault("llm_settings", {})
    s["model"] = model
    s["input_cost_per_1000_tokens"] = pin / 1000
    s["output_cost_per_1000_tokens"] = pout / 1000
    c["method_name"] = f"{c.get('method_name', 'run')} [{model}]"
    return c
