# Replication report — Phase 0/1 status (2026-10-05)

Verdicts on the papers' claims come in Phase 2. This file records infrastructure results and **upstream defects found by the module tests**.

## Gate P0 — met
| Check | Result |
|---|---|
| Both envs install; upstream imports | yes (Python 3.11.16, uv). MoHOLLM: `transformers` + `tabpfn` needed because `builder.py` imports them at module level; NB201/syne-tune skipped. Chimera: `langchain>=0.3,<1` (upstream uses `langchain.agents.AgentExecutor`, gone in 1.x). |
| `pytest -m offline` collects | yes |
| Live ping per model | 1 model (`minimax/minimax-m3`): 183 in / 30 out, ledgered $0.00009 (OpenRouter's own figure: $0.00007; our re-pricing is ~30% conservative) |
| Replay of the ping | $0.00 (ledger line `cached: true`) |

Deviations from the plan, all from user decisions or availability:
- **One model for both repos: `minimax/minimax-m3`** ($0.30/$1.20 per M tokens, reasoning model), replacing GPT-4o / Gemini-2.0-Flash / qwen. `google/gemini-2.0-flash-001` is no longer on OpenRouter anyway. Consequence: this is no longer a faithful same-model replication; it tests whether the *claims* transfer. Budget items merged: Chimera $6, MoHOLLM $4 (was $10+1.5 and $3+1).
- Reasoning tokens count as completion tokens and against `max_tokens`. Chimera hard-codes `max_tokens=1000`; the adapter raises it to 8000 so thinking cannot truncate the JSON answer.
- Cost hooking is at the HTTP transport (`common/openrouter.py`) instead of wrapping `update_cost_and_token_usage`; it covers both repos and failed calls.
- **Safety property added:** cap hits, replay misses and unpriced models raise `SandboxHalt(BaseException)`. Upstream wraps LLM calls in `except Exception` (MoHOLLM surrogate `while True: … retry`; Chimera per-week `except: no-op`), which would otherwise spin forever or silently turn a run into no-ops.

## Gate P1 — status
- Chimera: **88 passed, 1 skipped (TLC: no Java on this machine), 4 xfailed** (documented upstream bug).
- MoHOLLM: **106 passed**.
- **Chimera dynamics CSVs reproduce** (all 4, `atol=1e-6`): the downstream-Chimera hard gate is passed.
- `upstream/` of both repos is byte-identical to the source (`diff -rq`).
- `PAPER_TARGETS.md` written. MoHOLLM has **no numeric targets** (figures only); claims are ordinal.

## Upstream findings (each pinned by a test)
**Chimera**
1. `CSLGuardianEcom._violation_to_message` looks up the CSL violation *string* in a dict keyed by bare rule names, so 4 of 6 rules return a generic message. This text is what the LLM sees from `check_business_rules`. (strict xfail)
2. CSL guardian integer-rounds fields, so `ad_spend = -0.4` is "valid" while the legacy guardian rejects it. On 20k random actions every CSL/legacy disagreement lies within rounding distance of a rule boundary, and the rate is < 1%.
3. Seasonality floor 0.75 never binds at the default amplitude (min factor 0.8).
4. `CausalEngineV6` effect is exactly linear in the treatment: τ̂(no-op) = 0, τ̂(−a) = −τ̂(a), additive in price and ad spend, whereas the simulator is concave in ad spend. Against a Monte-Carlo ground truth (75 state×action cells): Spearman 0.88, sign agreement 0.92, RMSE 4.2k vs truth sd 8.0k. Useful for ranking, weak for magnitude. (`runs/results/causal_quality.csv`)
5. `run_agent_scenario` applies the guardian repair to Full Chimera too, although a comment says "non-Chimera agents".
6. Sensitivity table label ("150K empirically optimal") disagrees with its own numbers (see PAPER_TARGETS.md).

**MoHOLLM**
7. Config naming is inverted: `optimization_method: SpacePartitioning` is the paper's method (MOHOLLM-*.json), `mohollm` is the *global* baseline; `MOHOLLM-Penicillin-Gemini.json` is a 100-trial global run, not the partitioned method.
8. The paper configs use `region_acquisition_strategy: ScoreRegionRHVC` (+ cosine-annealing α in [0.01, 1]), not `ScoreRegionHVC` as the plan assumed. Both are tested; RHVC is what Phase 2 must run.
9. Of 7 schedulers, only `COSINE_ANNEALING` behaves as an α schedule; Constant/Linear/Cosine-decay/Step/Epsilon-greedy fail on `apply_settings`/`get_value`, and `EPSILON_DECAY` returns sample counts (default 100).
10. `VLMOP` benchmark is VLMOP3 (3 objectives); no ZDT/VLMOP JSON configs ship; ZDT scripts reference a missing `ZDT3/…` config.
11. `to_json` accepts only a ```json fence or the whole string; prose around bare JSON raises. A reasoning model that adds commentary will fail the sampler call.
12. `LLM_Surrogate_batch.evaluate_candidates` retries in an unbounded `while True`.
13. Categorical KD cells can share choices (banker's rounding on the index axis); range dims are disjoint and exactly cover the box.
14. Region probabilities use `scores / sum(scores)` with a possibly negative α-term; fine for α ≥ 0 (tested), would crash `np.random.choice` for sufficiently negative α. The builder's default α is 0.5, so it isn't hit by the shipped configs.
15. `save_progress` writes `./results/...` and the logger writes `.mohollm/log` relative to cwd: tests run in tmp dirs to keep upstream pristine.

## Open before Phase 2
- Read MoHOLLM's Fig. 3/4/6 from the PDF to fix the ordinal ablation targets.
- Decide seeds/evals: paper 10 seeds × 50 evals vs plan 3 seeds, and whether to run the repo's 57/65-eval configs.
- Pilot cost of minimax-m3 (reasoning tokens) before committing the $6 / $4 caps.

---

# Phase 2 pilot (2026-10-05) — `minimax/minimax-m3`, reasoning on

Protocol: pilot (Chimera 4 weeks, MoHOLLM 2 trials) → record → replay at $0 → project. **All pilots replay identically at $0** (Chimera 6/6 CSVs byte-identical; MoHOLLM fvals + configs identical, 0 live calls). Reaching that needed four harness fixes, three of them upstream non-determinism:

| # | Finding | Fix (in adapters/runners, upstream untouched) |
|---|---|---|
| 16 | Chimera's `AgentExecutor` streams; the non-streaming transport raised, upstream's per-week `except` turned **every week into a silent no-op** ("Connection error"), and the run still "completed" | `disable_streaming=True`; runner aborts if an agent made fewer LLM calls than weeks |
| 17 | Causal-forest estimates differ at ~1e-12 between processes; the float is embedded in the tool text the LLM reads, so the request key changed | round `estimate_causal_effect` to cents in the runner |
| 18 | MoHOLLM `candidate_sampler.py:175` `list(set(str))` orders candidates by `PYTHONHASHSEED`; upstream's `set_seed` sets it too late | runners re-exec with `PYTHONHASHSEED=0` |
| 19 | `shuffle_icl_rows=True` uses the global `random` shared by the partitioned method's 5 worker threads, so prompt order depends on thread timing | content-seeded shuffle patched in at import (regression test added) |
| 20 | reasoning model returns `content: null` at times (token budget / empty answer) → upstream "Failed to generate candidate. Retrying" | retry is upstream's; each retry is a paid call, counted in the ledger |

## Pilot measurements
**Chimera, 4 weeks (seed salt `seed0`, temp 0.9):**

| Agent | Bias | Profit | Trust | LLM calls | Cost | Time |
|---|---|---:|---:|---:|---:|---:|
| LLM-only | volume | 26,821 | 0.799 | 4 | $0.007 | 59 s |
| LLM+Guardian | volume | 107,740 | 0.760 | 30 | $0.032 | 281 s |
| Full | volume | 148,978 | 0.694 | 25 | $0.023 | 177 s |
| LLM-only | margin | 146,366 | 0.710 | 4 | $0.005 | 61 s |
| LLM+Guardian | margin | 165,300 | 0.698 | 28 | $0.028 | 170 s |
| Full | margin | 163,200 | 0.697 | 21 | $0.004 | 29 s |

Same arm (Full, volume) recorded twice gave 116,134 vs 148,978 — a ~28% spread at n = 1: single runs cannot support an ordering claim. Nothing else is read into 4-week numbers.

**MoHOLLM, Penicillin, 2 trials, seed 42:**

| Method | Calls | Output tokens | Cost | Time |
|---|---:|---:|---:|---:|
| global (`mohollm-Penicillin-Gemini-Context.json`) | 13 | 93.8k | $0.119 | 420 s |
| partitioned (`MOHOLLM-Penicillin-Context-Gemini.json`, RHVC) | 31 | 251.5k | $0.317 | 1339 s |

(Counts include retries. Trial 1 of the partitioned run had 1 region, trial 2 had 3, so its steady state — 5 regions — is more expensive per trial than the pilot average.)

## Projection against the caps
Reasoning dominates: ~8k output tokens per MoHOLLM call vs ~0.8k for a non-reasoning model.

| Run | Projection | Cap |
|---|---|---|
| Chimera R-C2, 52 weeks, 3 agents × 2 biases, **per seed** | ≈ $1.7, ≈ 3 h sequential | $6 total |
| MoHOLLM global, 13 trials, **per problem·seed** | ≈ $0.8, ≈ 45 min | $4 total |
| MoHOLLM partitioned, 15 trials, **per problem·seed** | ≈ $2.5–3.5, ≈ 3–4 h | $4 total |

- Chimera: 3 seeds ≈ $5 fits under $6 but leaves nothing for R-C3/C4/C5; 2 seeds ≈ $3.4 leaves ≈ $2.5.
- MoHOLLM: **one problem × one seed × both methods already costs ≈ $3.3–4.3, i.e. the entire $4 cap.** The plan's R-M1 (7 problems × 3 seeds × 2 methods) is out of reach by ~20× with reasoning on.
- Ledger now: Chimera $0.13 / $6, MoHOLLM $0.78 / $4 (a third of that is re-recordings forced by findings 18–19), total ≈ $0.92 / $25.

## Decision needed
Cheapest levers, in order: (a) reasoning effort low/off via OpenRouter's `reasoning` field (expected 5–10× cheaper; changes the model's behaviour, so it should be applied to both methods and all arms identically); (b) cut scope (fewer problems/seeds/trials); (c) raise the MoHOLLM cap by reallocating the unspent Phase 3/4 budget.

---

# Dependencies (2026-10-05)
- **JDK:** `brew install openjdk` (27, keg-only). **`tools/tla2tools.jar`:** TLA+ v1.8.0.
- **TLA+ proof re-run (Chimera): reproduced.** 174,268,417 states generated, **7,639,419 distinct, no error**, 54 s; identical to the paper's count. Discrepancy: the paper README's "diameter reached: 5" vs TLC's reported search depth 52 (different measure or a stale figure). Test `test_tlc_model_check` now runs it (marker `slow`).
- **HuggingFace / datasets:** none are used by the experiments in scope (Chimera data is bundled; NB201/fcnet out of scope).
- **TabPFN:** v2 weights fetched (open); upstream's `TabPFNRegressor()` would silently use the gated v3.5 with the installed package, so it is pinned to v2 in the adapter (test added: deterministic predictions, v3.x never fetched). User decision: TabPFN stays in as the R-M3 non-LLM surrogate.

---

# Reasoning-effort experiment (2026-10-05) — the "lower reasoning" plan does not work on minimax-m3

Added `SANDBOX_REASONING` (default|low|medium|high|off) to the transport (part of the cache key). Ran the MoHOLLM global pilot (Penicillin, 2 trials) under `low` and `off` and compared with the reasoning-on pilot. `max_tokens` 12,000.

| Setting | Surrogate calls | Mean out tokens | Truncated at cap, empty answer | Sampler calls: mean out tokens |
|---|---:|---:|---:|---:|
| default (on) | 44 | 7.3k | 12 (27%) | 7.7k |
| `effort: low` | 19 | 11.7k | 18 (95%) | 8.8k |
| `enabled: false` | 20 | 11.9k | 18 (90%) | **1.3k** (0 reasoning chars) |

- `effort: low` is not lighter than the default; it is heavier. `enabled:false` removes thinking for the candidate sampler but not for the surrogate prompt (predict 3 objectives for ~20 configs), where the model still reasons ~23k characters and runs out of tokens.
- Result: the `off` pilot cost $0.54 (39 calls) vs $0.12 for reasoning-on (13 calls); the `low` pilot entered upstream's unbounded retry loop (identical failing prompt, 12k tokens each) and was killed (~$0.4 of waste).
- Even at default, 27% of surrogate calls end empty at the 12k cap; upstream then retries.
- **Guard added:** an identical request sent live more than 3 times halts the run (`SandboxHalt`, `SANDBOX_MAX_LIVE_REPEATS`). Consequence: at a 27% failure rate a run can still abort on three consecutive failures of the same surrogate prompt (≈2% per surrogate call), so full runs need either a bigger token cap or an easier surrogate task.
- Ledger after this: total $1.54 / $25; MoHOLLM $1.41 of its $4 cap.

---

# MoHOLLM on `qwen/qwen3.7-flash` — pilot (2026-10-05, user decision: minimax-m3 stays for Chimera only)
Ledger item `mohollm_qwen` (cap $2). Penicillin, 2 trials, seed 42, `max_tokens` 12k, reasoning default.

| | Result |
|---|---|
| both pilots combined | 21 live calls, **$0.021**, ~7.3k output tokens/call (qwen also reasons; it is simply ~15× cheaper per call) |
| global baseline / partitioned wall time | 253 s / 834 s for 2 trials |
| empty/truncated answers | **1 of 21 (5%)** vs 12 of 44 (27%) on minimax-m3 |
| replay | both identical (fvals + configs), 0 live calls, $0 |

(The two pilots ran concurrently against one ledger item, so per-run call counts overlap; the combined figure is the reliable one.)

## Projection (MoHOLLM, qwen)
≈ 28 trials (13 global + 15 partitioned) per problem·seed ≈ 7× the 2+2-trial pilot ≈ **$0.15 and ≈ 2 h** per problem·seed.
- 7 problems × 3 seeds ≈ $3.1 (over the $2 cap) · 4 problems × 3 seeds ≈ $1.8 · 3 problems × 3 seeds ≈ $1.3.
- Wall time is the binding constraint: ≈ 2 h per problem·seed sequentially; 5 parallel processes ≈ 8 h for 4 problems × 3 seeds.
- Ledger now: total $1.56 / $25 (minimax MoHOLLM $1.41 is sunk on pilots/experiments; its cap is now unused).

---

# INTERIM results (2026-10-05) — Chimera R-C2 complete; MoHOLLM R-M1 partial (7 of 16 jobs)

## Chimera R-C2 — minimax-m3, 52 weeks, 3 seeds (market seed 42/43/44 + LLM sample), analysis: `chimera/runs/analyze_rc2.py`
Total profit, mean of 3 seeds (sd across seeds); loss-week share; final trust:

| Bias | Agent | Profit | sd | Loss weeks | Final trust |
|---|---|---:|---:|---:|---:|
| volume | LLM-only | 274,627 | 231,341 | 87% | 1.00 |
| volume | LLM+Guardian | 1,905,681 | 312,514 | 0% | 1.00 |
| volume | Full Chimera | 2,720,587 | 246,679 | 0% | 1.00 |
| margin | LLM-only | 2,140,557 | 242,661 | 0% | 0.69 |
| margin | LLM+Guardian | 2,918,823 | 58,109 | 0% | 1.00 |
| margin | Full Chimera | 2,703,001 | 847,284 | 0% | 0.89 |

Seed-paired differences (total profit, t-CI95, wins):
- volume: Guardian − LLM-only +1.63M [1.33M, 1.93M] 3/3; Full − Guardian +0.81M [−0.56M, 2.19M] 3/3; Full − LLM-only +2.45M [1.26M, 3.63M] 3/3.
- margin: Guardian − LLM-only +0.78M [0.32M, 1.24M] 3/3; Full − Guardian −0.22M [−2.46M, 2.03M] 2/3; Full − LLM-only +0.56M [−2.14M, 3.26M] 2/3.

Claim verdicts (provisional, n = 3):
1. *LLM-only fails under bias*: volume — **reproduced** (profit collapses to 0.27M vs 1.9M, 87% loss weeks; paper: −0.10M, 82.7%); margin — **not reproduced as a trust collapse** (final trust 0.69, Δ≈0, vs paper 0.36, Δ−0.33), but LLM-only is the lowest-profit arm.
2. *Guardian removes the failure*: **reproduced** under both biases (CIs exclude 0).
3. *Full > Guardian*: volume — direction holds 3/3 but CI includes 0; margin — **not reproduced** (−0.22M, 2/3; seed 1 Full collapsed to 1.73M). 
4. *Full has lowest weekly sd*: volume — yes (10.5k vs 17–18k); margin — no (7.2k vs 7.3k LLM-only, 8.3k Guardian). Lowest in 4 of 6 (bias, seed) cells.

Observations: absolute profits are ~1.5–3× the paper's (minimax-m3 is a different, likely stronger, model); trust saturates at its 1.0 clip under volume for both guarded arms; Full Chimera under margin is the highest-variance arm (sd 0.85M).

## MoHOLLM R-M1 (qwen3.7-flash) — operational findings so far
- Surrogate calls (1,624): 28.9% truncated at the output cap, 26.9% empty; sampler calls (1,382): 0.2% truncated. Mean output 10.1k vs 4.3k tokens. The surrogate prompt, not the sampler, drives cost and retries.
- 7 of 16 jobs finished. Only Penicillin seed 42 has both methods: at equal evaluations (53) HV 0.457 (MoHOLLM) vs 0.191 (global) (jointly normalised, ref 1.1; **n = 1, illustrative only**); MoHOLLM used 65 evaluations vs 57 and 292 vs 44 LLM calls.
