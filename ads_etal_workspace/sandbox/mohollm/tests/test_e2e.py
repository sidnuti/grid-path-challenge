"""End-to-end `main.py` path on configurations/Simple2D/mohollm-BraninCurrin.json with a RANDOM sampler and a scripted LLM
surrogate: the loop finishes, hypervolume is monotone non-decreasing, and the stats files are written."""
import json
import os
import random
from pathlib import Path

import numpy as np
import pytest
from pymoo.indicators.hv import HV

from benchmark_initialization import get_benchmark_fn
from mohollm.builder import Builder
from scripted_llm import ScriptedSurrogateLLM

pytestmark = pytest.mark.offline
UP = Path(__file__).resolve().parents[1] / "upstream"


def run(tmp_path, monkeypatch, seed=0, mutate=lambda c: None):
    (tmp_path / "prompt_templates").symlink_to(UP / "prompt_templates")
    monkeypatch.chdir(tmp_path)                      # upstream writes ./results/... relative to cwd; keep upstream pristine
    cfg = json.load(open(UP / "configurations/Simple2D/mohollm-BraninCurrin.json"))
    cfg.update(candidate_sampler="RANDOM_SEARCH_SAMPLER", seed=seed)
    cfg["llm_settings"]["model"] = "scripted"
    mutate(cfg)
    random.seed(seed)
    np.random.seed(seed)
    llm = ScriptedSurrogateLLM()
    bench = get_benchmark_fn(cfg)
    opt = Builder(config=cfg, benchmark=bench, custom_model=llm).build()
    top_k, stats = opt.optimize()
    return cfg, opt, llm, stats


def test_loop_finishes_13_trials_hv_monotone_and_stats_written(tmp_path, monkeypatch):
    cfg, opt, llm, stats = run(tmp_path, monkeypatch)
    st = opt.statistics
    n0, k, trials = cfg["initial_samples"], cfg["top_k"], cfg["n_trials"]
    assert trials == 13 and len(llm.calls) == trials                       # one surrogate prompt per trial
    assert len(st.observed_fvals) == n0 + trials * k == len(st.observed_configs)

    F = np.array([[f["F1"], f["F2"]] for f in st.observed_fvals])
    ref = F.max(0) * 1.1 + 1e-6                                           # fixed reference over the whole run
    hv = HV(ref_point=ref)
    curve = [hv(F[:n]) for n in range(n0, len(F) + 1)]
    assert all(b >= a - 1e-12 for a, b in zip(curve, curve[1:]))          # adding observations never lowers HV
    assert curve[-1] > curve[0]

    res = tmp_path / "results" / "BraninCurrin" / cfg["method_name"]
    assert res.exists() and any(res.rglob("*.csv"))
    assert set(p.name for p in res.iterdir()) >= {"observed_configs", "observed_fvals"}


def test_run_is_reproducible_under_a_fixed_seed(tmp_path, monkeypatch):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    a = run(tmp_path / "a", monkeypatch, seed=3)
    b = run(tmp_path / "b", monkeypatch, seed=3)
    assert a[1].statistics.observed_fvals == b[1].statistics.observed_fvals


def test_every_surrogate_prompt_carries_history_and_candidates(tmp_path, monkeypatch):
    _, opt, llm, _ = run(tmp_path, monkeypatch)
    for p in llm.calls:
        assert "Reference configurations with Known Performance" in p and "$" not in p.split("## Output Format")[0]
        assert p.count("Configuration: ") >= 5                              # at least the 5 warm-start observations


def test_no_llm_calls_other_than_surrogate_when_sampler_is_random(tmp_path, monkeypatch):
    _, _, llm, _ = run(tmp_path, monkeypatch)
    assert all("Candidate configurations to Evaluate" in p for p in llm.calls)
