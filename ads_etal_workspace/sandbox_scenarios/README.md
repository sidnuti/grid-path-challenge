# sandbox_scenarios: Grid Market Simulator v2 + MoHOLLM (WIP)

This folder extends the grid-path-challenge ad simulator so it represents situations brands actually face:
- category cannibalization, on a shelf with siblings and competitors;
- brand-owned queries;
- festive, seasonal and short-lived demand, with stock limits;
- competitor bidding.

It also adds a true incremental-revenue scorer, and tests MoHOLLM against it on progressively harder goals:
- E1: one objective;
- E2: three objectives;
- E3: binding constraints.

The folder is self-contained. **The repo's own `gpc/` is not modified**, because the simulator v2 lives in `gpc_v2/` as its own copy of the package.

- Plan: `plan/2026-10-05_sandbox_ads_e2e_plan.md`.
- Spec: `design/` (docs 01–05, plus the HTML site).
- Phase logs: `logs/`.
- Results: `results/`.

## Layout

| Path | What |
|---|---|
| `gpc_v2/gpc/` | The `gpc` package with sim v2 (modules A–F, scenarios `sc1_cannibal` … `sc_all`). Every v2 mechanism is off unless a scenario turns it on, so `dev` reproduces the legacy output byte for byte. |
| `gpc_v2/SIM_V2_CHANGES.patch`, `COMMITS.txt` | The exact diff against this repo's `gpc/` at 202a9ca, and the commit messages it came from. |
| `gpc_v2/tests/` | `v2/` (43 gates: shelf, scorer, intent, calendar, stock, competitors, holdout, calibration) and `test_goldens.py`, which checks the legacy goldens in `tests/goldens/` (4 seeds × {no_op, traversal}). |
| `gpc_v2/scripts/` | `make_goldens.py`, `make_scenarios.py` (all scenario files are generated here), `calib_v2.py`, `p2_readout.py`. |
| `bench/` | The Track-A decision vector (`decode.py`), guardrail-free sim loop (`sim.py`), goals and constraint slacks (`goals.py`), cached black box (`blackbox.py`), shared Sobol design, the non-LLM arms A0/A1/A2 and oracle O1 (`arms.py`), and `report.py`. |
| `mohollm/adapters/` | `grid_market.py` (`GridMarketBenchmark`), `ads_configs.py` (A3/A4/A5 configs), `ads_acq.py` (RandomTopKACQ, see upstream finding below), `scripted_ads_llm.py` (offline LLM), `ledger_hook.py` (OpenRouter through the cache and ledger). |
| `mohollm/runs/r_ads.py` | Runs one MoHOLLM arm on the ads benchmark. |
| `mohollm/tests/test_ads_bench.py` | 17 offline gates, including end-to-end A3/A4 (scripted LLM) and A5 (no LLM). |
| `common/` | OpenRouter `CachingTransport` (record/replay, wall-clock deadline, retry-storm guard) and the ledger. **Every paid cap is $0** until approved. |

Not committed (see `.gitignore`):
- virtualenvs;
- `mohollm/upstream/`;
- caches, run outputs, the ledger.

## Restore

```bash
cd ads_etal_workspace/sandbox_scenarios
# MoHOLLM upstream, never edited: copy the source tree recorded in mohollm/UPSTREAM.txt
rsync -a --exclude .git ~/Documents/Exploration/mohollm/ mohollm/upstream/
# simulator env (Python 3.11)
uv venv --python 3.11 gpc_v2/.venv && uv pip install --python gpc_v2/.venv/bin/python -r gpc_v2/requirements.txt pyarrow hypothesis cma tabulate
# MoHOLLM env (Python 3.11; botorch, pymoo 0.6.0)
(cd mohollm && uv sync)
```

The OpenRouter key is read from the repo-root `.env` (`OPENROUTER_API_KEY`). It is never printed or logged. Offline runs default to `SANDBOX_LLM_MODE=replay`, so they cannot spend.

## Run

```bash
# simulator v2 gates and the legacy goldens (gpc_v2 must come first on the path, ahead of the repo's gpc/)
(cd gpc_v2 && PYTHONPATH=. .venv/bin/python -m pytest -q tests/v2 && PYTHONPATH=. .venv/bin/python scripts/make_goldens.py --check)
# benchmark + MoHOLLM adapter gates, offline
(cd mohollm && uv run pytest -q tests/test_ads_bench.py ../common/tests)
# one $0 MoHOLLM arm (A5: partitioned, random in leaf, no LLM), and a scripted-LLM A4
(cd mohollm && uv run python runs/r_ads.py --arm A5 --scenario sc1_cannibal --seed 7 --goal G0 --evals 50)
(cd mohollm && uv run python runs/r_ads.py --arm A4 --scenario sc1_cannibal --seed 7 --goal G0 --evals 20 --scripted)
# non-LLM arms and the CMA-ES oracle (O1 runs in the gpc_v2 env: pymoo 0.6.0 pins cma 3.2.2, which breaks on numpy 2)
(cd mohollm && PYTHONPATH=..:../gpc_v2 uv run python -m bench.arms --arm A2 --scenario sc1_cannibal --seed 7 --evals 50)
PYTHONPATH=.:gpc_v2 gpc_v2/.venv/bin/python -m bench.arms --arm O1 --scenario sc1_cannibal --seed 7 --evals 1000 --workers 8
# the full $0 baseline sweep
sh logs/p3_sweep.sh 1000
```

## Status (2026-10-05)

| Phase | State |
|---|---|
| P0 setup, legacy goldens | done |
| P1 16× faster market (byte-identical), Module A nested-logit shelf, Module F ads-off scorer | done |
| P2 Module B intent mix, C calendar and stock, D competitor agents, public tables, holdout lever, 5 scenarios | done; `results/p2/SUMMARY.md` |
| P3 decoder, black box, A0/A1/A2/A5/O1, MoHOLLM adapter (A3/A4/A5), offline end to end | built and tested. **Baseline sweep and O1 still to run**; `results/p3/` has smoke runs only |
| P4 constraint compiler and verifier (C1–C9) | not started |
| P5 paid MoHOLLM pilot, then E1/E2/E3 | needs an approved cap |
| P6 analysis, verdicts on H1–H8 | not started |

Modelling decisions and every deviation from `design/` are in `logs/P2_log.md` and `logs/P3_log.md` (README items M1–M11, D1–D9, and the P3 decisions).

Upstream MoHOLLM finding: `RandomACQ` ignores `top_k` and returns a single int, so the partitioned loop fails with a TypeError at `space_partitioning_mohollm.py:142`. A $0 random-in-leaf arm therefore needs `adapters/ads_acq.py`, which is registered at runtime.
