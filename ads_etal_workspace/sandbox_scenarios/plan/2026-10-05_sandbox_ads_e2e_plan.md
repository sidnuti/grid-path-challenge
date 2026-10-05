# sandbox_ads/ — Grid Market Simulator v2 + MoHOLLM, end to end

## Context
The design in `system_design_proposals/grid_design_simulator/` (docs 01–05) extends the grid-path-challenge ad simulator with:
- category cannibalization;
- brand-loyal vs open shoppers;
- festive and seasonal demand, stock limits and competitor price inflation;
- an "ads-off" counterfactual scorer.

It then tests MoHOLLM on harder and harder goals: E1 one objective, E2 a trade-off curve between objectives, E3 binding constraints C1–C9 with and without a compiler.

Nothing is built yet. This plan creates a clean, self-contained `sandbox_ads/` workspace holding:
- fresh clones of the simulator and MoHOLLM;
- the design docs;
- the reusable sandbox plumbing.

It then implements the work in gated phases. Everything is $0 until the paid MoHOLLM pilot, which needs your approval and a new budget cap.

Assumption: "grid-planning*" means `grid-path-challenge`. No `grid-planning*` folder exists anywhere under `~/Documents`.

## Workspace layout (`/Users/arnabkar/Documents/Ads-etal/sandbox_ads/`)

- **`design/`**: copy of docs 01–05, the README and the HTML site; this is the source spec.
- **`gpc/`**: `git clone` of the local grid-path-challenge.
  - Branch `arnab/l2p_intent_compiler` at 202a9ca; new branch `ads/sim-v2`.
  - `.env` is not copied. The key is still read from the original `grid-path-challenge/.env`.
- **`mohollm/`**
  - `upstream/` is an rsync of `~/Documents/Exploration/mohollm` @ d7f960e (no `.git`) and is never edited.
  - `adapters/`, `runs/`, `tests/` are seeded from `sandbox/mohollm/*`, including `ledger_hook.py`, `r_m1.py`, the scripted LLM and the 108 tests.
- **`common/`**: copy of `sandbox/common`:
  - `openrouter.py` (CachingTransport, deadline, retry-storm guard);
  - `ledger.py`, with its own ledger file and new caps;
  - `stats.py`.
- **`bench/`**: new glue package; see Phase 3.
- **`runs/`, `logs/`, `REPORT.md`, `README.md`**

Python 3.11 via uv. Two environments: `gpc/` (numpy, pandas, scipy, pydantic, plus Hypothesis, z3-solver, pulp/HiGHS, cma) and `mohollm/` (upstream deps plus BoTorch). `bench/` is importable from the mohollm environment, with gpc installed into it editable.

## Phases

### P0: Setup and baseline ($0)
1. Create the layout above, then clone, rsync and copy. Write `UPSTREAM.txt` files recording the source and commit.
2. Create the environments.
3. Run the baseline tests:
   - gpc: `make test`, and `harness-test` should give 132 passing with 8 deselected;
   - mohollm: 108 tests;
   - common: 13 transport tests.
4. Record a **legacy golden** set: `simulate(build_world(s), NoOp | DeterministicTraversal)` output tables for seeds 7, 11, 23 and 42, stored as parquet with hashes.

Gate: all tests pass and the goldens are recorded.

### P1: Simulator speed + Modules A (shelf) and F (scorer v2) ($0)
1. **Vectorise `simulate_day`** in `gpc/market.py`: numpy over pairs × dayparts × slots, removing the per-SKU pandas filter.
   - Gate: byte-identical to the goldens.
   - Target under 1.5 s per 70-day world. A black-box evaluation must be fast, because the oracle alone needs 2,000 evaluations.
2. **Child RNG streams:** new mechanisms draw from `SeedSequence([seed, 1009, day, MODULE_ID])`, so legacy draws never shift.
3. **`gpc/shelf.py`** (flag `shelf_model: legacy|nested_logit`):
   - competitor items V1, V2, N1, N2 and the bar/liquid nests;
   - diversion ratios stored in `truth["diversion"]`;
   - the 4-way split of each ad order (self / sibling / competitor / expansion).
   This replaces only step 6 of `market.py`.
4. **`gpc/score_v2.py`:** a common-random-numbers ads-off rerun, bypassing the guardrails.
   - Reports IncRev^brand, iROAS, the decomposition per cell/SKU/nest/phase, and the legacy score.
   - Reuses the ideas in `ads_etal_workspace/experiments/lib/{oracle.py,direct_sim.py}`.
5. Scenario `sc1_cannibal.json`.

Gates (doc 02 §10, steps 1, 2 and 5):
- flags off gives the legacy output exactly;
- λ = 1 reduces to plain logit (IIA);
- diversion rows sum to ≤ 1;
- the CALIBRATION.md ranges hold;
- IncRev(no_op) = 0;
- the decomposition sums to attributed orders;
- the same seed gives the same counterfactual.

### P2: Modules B, C, D and the scenarios ($0)
- **`gpc/intent.py`:** the per-query/city mix π (Aurel/Velora/Nimbus/open), stealing, reformulation and city tilt.
- **`gpc/calendar.py` + `gpc/stock.py`:** festive and seasonal curves, pull-forward, K11/S6 as short-lived items, stock that stops ads when it runs out, salvage.
- **`gpc/competitors.py`:** competitor pacing that inflates prices at festive time, plus opportunistic bidding on K01.
- New public tables (`shelf_daily`, `category_share_weekly`, `calendar_public`, `lift_readout`) and the `request_holdout` lever.
- Scenarios: `sc2_brand_assoc`, `sc3_festive`, `sc4_seasonal`, `sc_all`.
- Re-run the linkage EDA against the v2 truth.

Gates:
- units conserved under pull-forward, and stock ≥ 0;
- festive CPM ratio in [1.3, 1.5];
- holdout confidence interval covers the truth ≥ 90% of the time over 50 seeds;
- each scenario runs in under 30 s per world (goal: under 3 s).

### P3: Black-box benchmark, baselines, oracles, and the MoHOLLM adapter ($0)
1. **`bench/decode.py`**: a pure function `decode(x, obs) → actions`. It applies doc 04 §2.1 with three fixes for issues found in review:
   - stick-breaking over 3 regions uses **2** dimensions, so the vector is 11-d, not 12;
   - E1 fixes total spend at B, so the budget-scale dimension is dropped for E1 and kept as an option for E2/E3;
   - C1 is restated as "6-week spend ≤ B, run spend ≤ B/6 × 1.5".
   `encode⁺` is its least-squares inverse.
2. **`bench/blackbox.py`**: `f(x, scenario, seed, goal_level) → {objectives, constraint values, diagnostics}`. Results are cached on disk by hash(x, scenario, seed, code version).
3. **Non-LLM arms**:
   - A0: no-op and traversal;
   - A1: Sobol random search;
   - A2: BoTorch qLogEI (E1) / qLogEHVI (E2);
   - A5: partitioned search with random sampling in each leaf instead of the LLM;
   - O1: CMA-ES, 2,000 evaluations × 10 restarts;
   - O2 (exact MILP on the true parameters) is deferred and optional.
4. **`mohollm/adapters/grid_market.py`: `GridMarketBenchmark(BENCHMARK)`**, implementing the methods of `upstream/mohollm/benchmarks/benchmark.py:10`:
   - `generate_initialization`;
   - `evaluate_point`, which returns `(point, {F1..})` and must keep the key order fixed;
   - `is_valid_candidate`, a cheap bounds check only. Penicillin re-evaluates the simulator here; we must not.
   - `benchmark_name`, `method_name`, `model_name`, `problem_id` and `seed` must be set for `save_progress`.

   Facts that shape the adapter:
   - **No upstream edit:** the registry in `benchmark_initialization.py:24` is a hardcoded `match`. A new runner, `runs/r_ads.py` (cloned from `r_m1.py`), passes the instance as `Builder(cfg, benchmark=GridMarketBenchmark(...))`.
   - **Minimisation is assumed everywhere:** `metrics_targets` is ignored. So F1 = −IncRev, F2 = −North S5 share, F3 = −S6 sell-through.
   - **No constraint support:** E3's `-penalty`, `-reject`, `-prompt` and `+compiler` arms are implemented in our benchmark wrapper and runner:
     - penalty: violation added to the objectives;
     - reject: `is_valid_candidate` for action-class rules;
     - prompt: constraint text in `prompt.description`;
     - compiler: repair inside `evaluate_point`, logging the repaired point.

     Infeasible evaluations must never return `None`, because that breaks the hypervolume code (see ChankongHaimes).
   - **E1 is single-objective:** `ScoreRegionRHVC` raises an error with fewer than 2 metrics. E1 uses `ScoreRegion` with `FunctionValueACQ`, or E1 is run as 2 objectives (−IncRev, spend); decide after the scripted run.
   - **Configs:** JSON files in `mohollm/configs/ads/` cloned from the Penicillin pair:
     - A4: `SpacePartitioning`, kdtree, RHVC, cosine-annealing α, `m0` 5;
     - A3: `mohollm` global.

     Both have `prompt.description` written in plain words for the 11 decision variables.
   - **$0 baselines in the same loop:** `RANDOM_SEARCH_SAMPLER` with `GAUSSIAN_PROCESS_SURROGATE_BOTORCH` or `TABPFN_SURROGATE`, plus partitioned `RANDOM_SEARCH_SAMPLER` (A5). A standalone BoTorch qLogEHVI script serves as A2.
   - **Reporting hypervolume:** fixed reference points per scenario, from no-op and O1 (pymoo `HV`, as in `upstream/plot/plot_settings.py`).
   - **Cost risks:** the surrogate retries in an unbounded `while True` (`llm_surrogate_batch.py:60`), so we rely on the retry-storm guard and deadline from `common/openrouter.py`. Each partitioned trial makes about 10 or more calls.
5. **End-to-end test at $0** using the scripted LLM: A4 runs 10 trials on sc1 and writes `result.json` and the hypervolume.

Gate: every arm runs end to end offline. O1 sets the regret reference.

### P4: Compiler and verifier ($0)
- **`gpc/compiler/`** has three parts:
  - the constraint IR, with money in paise;
  - load-time checks: typing, Z3 consistency, a feasibility MILP returning an IIS (the set of conflicting rules) and reachability;
  - the runtime pipeline: verify → clamp/block → L1-minimal LP projection (C5, C6) → trim (C4, C7) → buffered chance constraint (C9) → certify.
- Reason codes and a goal ledger, giving a cost for each goal.
- E3 arms: `-blind`, `-prompt`, `-penalty`, `-reject`, `+compiler-repair` (feed back `encode⁺`), `+compiler-box`.
- Tests:
  - Hypothesis soundness, idempotence and minimality;
  - no-op safety;
  - a differential test against `apply_guardrails` over `data/runs/*`.
  - TLC is available, since Java is installed at `/opt/homebrew/opt/openjdk`.

### P5: Paid MoHOLLM runs (**needs your approval and a new cap**)
- Model: `qwen/qwen3.7-flash`; `PYTHONHASHSEED=0`; record mode, then replay-verify at $0.
- Wall-clock deadline and auto-resume carried over from the sandbox.
1. Pilot: 2 evaluations per LLM arm on sc1 → replay → cost projection → ask you for the cap.
2. E1: arms A1–A5 × sc1, sc2, sc3, sc_all × 3 seeds × 50 evaluations (100 if budget allows), then re-score on 5 held-out seeds.
3. E2: the G-1 ladder (3 objectives), scored by hypervolume.
4. E3: the C1–C9 arms; tests H4–H7.

### P6: Analysis and report
Paired statistics (`common/stats.py`), verdicts on hypotheses H1–H8, and the goal-ledger explanations. Output is `REPORT.md`, plus the design HTML site updated with results.

## Reused code
- `sandbox/common/openrouter.py`, `ledger.py`, `stats.py`
- `sandbox/mohollm/adapters/ledger_hook.py`, `runs/r_m1.py`, `tests/scripted_llm.py`
- `gpc/world.py`, `market.py`, `runner.py`, `guardrails.py`, `score.py`
- `harness/tools/precheck.py`, `sizing.py`, `incrementality.py` (for the compiler and the projection)
- `ads_etal_workspace/experiments/lib/oracle.py`, `direct_sim.py`

## Verification
- Every phase ends with a pytest gate: legacy goldens are byte-identical, plus the doc 02 §10 gates and the doc 05 §5 compiler tests.
- One command runs the end-to-end scripted check:
  `uv run python bench/e2e.py --arm A4 --scripted --scenario sc1`
- Paid runs must replay at $0 with identical results before any statistics are run.

## Open items (resolved as information arrives)
- E1's single-objective set-up: `ScoreRegion` + `FunctionValueACQ`, or 2 objectives (IncRev, spend).
- Whether to finish the in-flight sandbox R-M1 qwen runs before starting P5. Both use the same OpenRouter key, and the budgets are separate.
- The budget cap for P5, set from the pilot.
