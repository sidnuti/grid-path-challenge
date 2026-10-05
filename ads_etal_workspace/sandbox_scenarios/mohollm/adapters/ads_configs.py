"""MoHOLLM configs for the ads arms (design/04 §3.1), derived from the shipped Penicillin pair so every setting
not listed here is the paper's.

  A3  global MoHOLLM (`optimization_method: mohollm`; upstream's inverted naming, REPLICATION finding 7)
  A4  partitioned MoHOLLM (`SpacePartitioning`, kd-tree, ScoreRegionRHVC, cosine-annealed α: the paper's method)
  A5  A4 with the LLM replaced by random sampling in the selected leaf (random sampler and surrogate, RandomTopKACQ)

Evaluation budget n: 5 shared initial points + top_k per trial. With top_k = 5, n = 5 + 5·n_trials.
Single-objective goals (E1) cannot use ScoreRegionRHVC (it raises with < 2 metrics) or hypervolume acquisition:
they use ScoreRegion + FunctionValueACQ.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

UP = Path(__file__).resolve().parents[1] / "upstream" / "configurations"
PARTITIONED = UP / "Penicillin" / "MOHOLLM-Penicillin-Context-Gemini.json"
GLOBAL = UP / "Penicillin" / "mohollm-Penicillin-Gemini-Context.json"
TOP_K = 5


def make_config(arm: str, bench, evals: int = 50, description: str = "") -> dict:
    base = json.loads((GLOBAL if arm == "A3" else PARTITIONED).read_text())
    cfg = copy.deepcopy(base)
    dims, metrics = bench.dims, bench.metrics
    n_trials = max(1, (evals - 5) // TOP_K)
    cfg.update({
        "method_name": f"{arm} ({bench.problem_id})",
        "benchmark": "grid_market", "benchmark_settings": {},
        "initial_samples": 5, "top_k": TOP_K, "n_trials": n_trials, "total_trials": n_trials,
        "range_parameter_keys": dims, "float_parameter_keys": dims, "integer_parameter_keys": [],
        "parameter_constraints": {k: [0.0, 1.0] for k in dims},
        "metrics": metrics, "metrics_targets": ["min"] * len(metrics),
        "warmstarter": "RANDOM_WARMSTARTER",
        "prompt": {"description": description},
    })
    if arm in ("A4", "A5"):
        sp = cfg["space_partitioning_settings"]
        if len(metrics) < 2:
            sp["region_acquisition_strategy"] = "ScoreRegion"
    if len(metrics) < 2:
        cfg["acquisition_function"] = "FunctionValueACQ"
    if arm == "A5":
        cfg.update(candidate_sampler="RANDOM_SEARCH_SAMPLER", surrogate_model="RANDOM_SEARCH_SURROGATE",
                   acquisition_function="RandomTopKACQ")       # adapters/ads_acq.py (upstream RandomACQ ignores top_k)
    return cfg
