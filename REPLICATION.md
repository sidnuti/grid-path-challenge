# Replication: L2′ intent compiler (branch `arnab/l2p_intent_compiler`)

This branch builds on `arnab/wip-m1-m5-system-1` (System 1 harness, M0–M6). It adds **L2′**: an expressive LLM
planner whose typed intent plan is turned into guardrail-safe actions by a deterministic **L0 intent compiler**.
It also carries the experiments, findings, runtime feedback and logs needed to reproduce every number reported
so far.

Snapshot taken 2026-10-04. Some LLM runs were still in progress at that time (see *Status* below).

## What is where

| Path | What |
|---|---|
| `harness_l2p/` | L2′ package: `brief.py` (observation-only state brief with refs), `intents.py` (IntentPlan schema), `compiler.py` (intent → actions, precheck, allowance), `rules_planner.py` (deterministic LLM ablation), `planner.py` + `prompts/L2P_plan.v{1,2}.md`, `llm.py` (OpenRouter reasoning client, priced meter), `policy.py` (`L2PHarness`, fail-soft to L0) |
| `tests/harness_l2p/` | 29 tests: import isolation (no `.truth`/scenarios/`harness_eval`), schema clip, each verb → lever, guardrail limits, conflicts, every fail-soft path |
| `llm_cache/` | record/replay cache of every real LLM call (1,160 responses). Lets the LLM arms be re-scored at $0 with `LLM_MODE=replay` |
| `scripts/setup_replication_workspace.sh` | rebuilds the sibling layout the experiment code expects |
| `ads_etal_workspace/experiments/` | experiment harness: `lib/` (runs cache, stats, arms, scripted/oracle planners), X0–X8 runners, `results/*.md|json|log`, `results/x8_spend.jsonl` (LLM spend ledger) |
| `ads_etal_workspace/experiments/x8_l2prime/` | `x8_run.py` (run/report), `x8_detail.py` (what the LLM arms changed vs L0) |
| `ads_etal_workspace/system_design_proposals/` | `01` S1/Measurement/S2 coupling, `02` notebook diagrams, `03` L2′ expressiveness and scale report (draft) |
| `ads_etal_workspace/runtime_findings/` | FINDINGS, NEXT_STEPS, per-experiment results |
| `ads_etal_workspace/runtime_feedback_improvement/` | runtime feedback report, probe scripts, outputs |
| `ads_etal_workspace/explore_eda/` | EDA report, scripts, figures, SKU tier CSVs (the nested clone of the upstream repo is omitted) |
| `ads_etal_workspace/logs/` | build/experiment logs; `x8_runtime/` holds the raw X8 run logs (prefixed by session) |
| `ads_etal_workspace/plan_copies/` | approved plans, including `2026-10-04-l2prime-expressive-arm-and-scale-plan.md` |
| `ads_etal_workspace/requirements-freeze.txt` | exact package versions used (Python 3.9.6, macOS) |

Not included: `experiments/results/cache/*.pkl` (13 GB of cached simulations). These are regenerated on demand.
The cache key includes a hash of `gpc/`, `harness/` and `harness_l2p/` (`experiments/lib/runs.py:code_hash`).

## Setup

```bash
scripts/setup_replication_workspace.sh ~/gpc_ws
```

```bash
cd ~/gpc_ws/grid-path-challenge
```

All commands below run from `~/gpc_ws/grid-path-challenge` with `PYTHONPATH=.:..`. Record mode needs
`OPENROUTER_API_KEY` in `.env`. Replay mode needs no key.

## 1. Tests

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q tests/harness_l2p
```

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q tests -m "not slow"
```

Expected: 29 passed, then 132 passed with 8 deselected.

## 2. Free arms (no LLM, $0): bounds and gate A

```bash
PYTHONPATH=.:.. .venv/bin/python -m experiments.x8_l2prime.x8_run run --worlds dev6 --jobs 6 --arms l0 baseline no_op l2p_aug_rules l2p_nat_rules l2p_aug_random l2p_nat_random l2p_aug_oracle l2p_nat_oracle
```

```bash
PYTHONPATH=.:.. .venv/bin/python -m experiments.x8_l2prime.x8_run report --worlds dev6 --arms no_op l2p_aug_rules l2p_nat_rules l2p_aug_random l2p_nat_random l2p_aug_oracle l2p_nat_oracle
```

Repeat with `--worlds pert3`, the three perturbed worlds. Use `--worlds fresh6` (seeds 3001–3006) only for the
one-time confirmation of the best arm. Each simulation takes about 50–140 s.

## 3. Real-LLM arms (qwen/qwen3.7-flash via OpenRouter, reasoning on)

To re-score from the committed cache at $0, with no network access, set replay mode first:

```bash
export LLM_MODE=replay
```

```bash
PYTHONPATH=.:.. .venv/bin/python -m experiments.x8_l2prime.x8_run run --worlds dev6 --jobs 6 --arms l2p_aug_llm_r0 l2p_nat_llm_r0 l12_llm_r0
```

```bash
PYTHONPATH=.:.. .venv/bin/python -m experiments.x8_l2prime.x8_run report --worlds dev6 --arms l2p_aug_llm_r0 l2p_nat_llm_r0 l12_llm_r0
```

```bash
PYTHONPATH=.:.. .venv/bin/python -m experiments.x8_l2prime.x8_detail
```

Without `LLM_MODE`, the runner defaults to `record`: it serves cache hits and pays only for misses. The per-run cap
is $0.25 and the ledger-wide cap is `--cap 10` (from `experiments/results/x8_spend.jsonl`, repriced from tokens).

Replay matches only when the prompt bytes match. The brief, the prompt file and the model are all in the cache
key. A cache miss in replay mode raises an error; it never silently calls the API.

Arm names:
- `l2p_{aug|nat}_{rules|random|oracle|llm}[_r<k>]`
- `l2pv2_*`: the same arms after revision 2 (prompt v2, protected cuts)
- `l12_llm_r<k>`: the existing HTN harness at depth L2 with the real model, for comparison

`aug` merges the intents with L0's candidates. `nat` ships the intents only, with L0 as compiler and safety.
`oracle` reads hidden truth and is offline only.

## Findings so far

**Free arms on dev6, paired lift vs L0 (offtake, eval window), all floors met (6/6):**

| arm | vs L0 | better/worse | p (sign-flip) |
|---|---|---|---|
| oracle intents, native | **+0.96%** | 6/0 | 0.031 |
| oracle intents, augment | **+0.88%** | 6/0 | 0.031 |
| rules planner, native | +0.21% | 5/1 | 0.19 |
| rules planner, augment | +0.11% | 5/1 | 0.50 |
| no-op | −0.07% | 3/3 | 0.25 |
| random intents, augment / native | −0.62% / −0.86% | 1/5, 0/6 | 0.06 / 0.03 |

**Gate A passed.** Oracle intents through the same compiler beat L0 by more than the MDE. X5.1's oracle *leaves*
gave about 0. So the intent interface can express gains that the L1/L2 leaves cannot. The full table is in
`ads_etal_workspace/experiments/results/x8_l2prime_dev6.md`.

**Real LLM, replicate 0 on dev6** (`results/x8_detail.md`):

| arm | vs L0 | better |
|---|---|---|
| L0 + L1/L2 (`l12_llm`) | +0.01% | 1/6 |
| L0 + L2′ (`l2p_aug_llm`) | −0.09% | 2/6 |
| L2′ native (`l2p_nat_llm`) | −0.42% | 2/6 |

All floors were met. The LLM cut spend about 6% vs L0 (mostly budget cuts on trim campaigns) and did not
reallocate enough to growth cells. Revision 2 (`l2pv2_*`: prompt v2, protected cuts) targets this and was still
running when the snapshot was taken.

**Cost:**
- L2′ plan call: about 10–24k tokens in, 8–17k out, 70–130 s, about $0.0015–0.003 per call.
- The ledger shows about $3.1 total. The `l12_llm` rows carry the harness Meter's $3/$15 fallback price; repriced from tokens they are cents.

## Status at snapshot

- Done: the L2′ package and its tests, the free-arm bounds on dev6 and pert3, and real-LLM replicate 0 on dev6
  (plus parts of r1/r2).
- In progress or pending: the remaining real-LLM replicates, the `l2pv2_*` LLM arms, the one-time fresh6
  confirmation, and the placeholders in `system_design_proposals/03_…` (`{{RESULTS}}`, `{{COST}}`, `{{LATENCY}}`).
- Seeds spent: dev6 (7, 11, 23, 42, 101, 202), pert3 (303, 304). Fresh6 (3001–3006) is unspent.
- `harness/`, `gpc/market.py`, `guardrails.py`, `runner.py` and `score.py` are unchanged by this branch.
