# Plan: replicate Chimera and MoHOLLM in `sandbox/`, adapt them to L2″, then extend the grid environment

## Context

The previous turn produced `explore-and-understand/03–05`.
- **03 (Project Chimera)** found three ideas worth having: multiple hypotheses, a guardian that rules on each one, and a causal value model.
- **04 (MoHOLLM)** found one: partition the space into boxes, score them like bandit arms, and let the LLM propose inside the chosen box.
- **05** proposed **L2″**: a top-down exact allocator (MILP, solved by branch-and-bound, plus OT), a GoalSpec, and a decision record that gives a reason for every lever option. This answers the call's gaps: macro-level optimization, "why were the alternatives rejected", and persona goals.

It also found that several published claims could not be verified from the repositories:
- Chimera ran n = 1 per arm, and its trust numbers are absolute, not %.
- The MoHOLLM benchmark table cited in the earlier Exploration reports is not in the repo.

So before building on either paper, we **re-run them ourselves**, with tests per module, routing all LLM calls through **OpenRouter**. Then we adapt the ideas to our harness, and then extend the grid environment so the new use cases (regional goals, SKU/city totals, launch share-of-voice (SOV), heterogeneous goals, price of safety) can be measured.

**Decisions (from the user):**
- **Models:** each paper's own model via OpenRouter (`openai/gpt-4o` for Chimera, `google/gemini-2.0-flash-001` for MoHOLLM) to replicate faithfully, then `qwen/qwen3.7-flash` to test transfer.
- **Budget:** **new programme cap of $25**, separate ledger.
- **MoHOLLM scope:** the **core subset**. Synthetic (BraninCurrin, ZDT1/2, DTLZ2, VLMOP2) plus real-world (Penicillin, VehicleSafety, CarSideImpact). Ablations on Penicillin. Skip NB201/fcnet (Syne-Tune).
- **Sandbox layout:** upstream code **copied into `sandbox/`**. The Exploration clones stay untouched.

**Order and gating:**

```
Phase 0  sandbox + OpenRouter shim
Phase 1  offline module tests ($0)
Phase 2  paid replication  →  replication verdicts
Phase 3  adapt into harness_l2p on the unchanged env (X9a)
Phase 4  extend the grid environment + X9b
```

Each phase has a gate. A failed gate changes what the next phase builds; it does not silently continue.

---

## Phase 0: sandbox and shared infrastructure

**Layout** (under `/Users/arnabkar/Documents/Ads-etal/sandbox/`):

```
sandbox/
  README.md                      how to run, envs, ledger, gates
  common/
    openrouter.py                OpenRouter chat client: record/replay cache, $ ledger, model price table
    ledger.py                    programme ledger sandbox/ledger.jsonl, hard cap $25, per-phase sub-caps
    stats.py                     thin re-export of experiments/lib/stats.py (paired t-CI, sign-flip, bootstrap)
  chimera/
    upstream/                    copy of ~/Documents/Exploration/Project-Chimera (commit hash in UPSTREAM.txt)
    adapters/llm.py              make_chat_llm(model, temperature) → langchain ChatOpenAI(base_url=openrouter) wrapped by common cache/ledger
    adapters/scripted_llm.py     deterministic fake chat model for offline tests (tool-calling transcript replay)
    tests/                       pytest, markers: offline | paid | slow
    runs/                        replication scripts (r_c1…r_c5), results/*.csv, REPORT.md
    pyproject.toml               uv env, Python 3.11, pinned from upstream requirements (econml, shap, langchain-openai, csl-core, z3)
  mohollm/
    upstream/                    copy of ~/Documents/Exploration/mohollm (commit hash recorded)
    adapters/                    config overlays: llm_settings.model → OpenRouter model ids; OPENROUTER provider (already in upstream: mohollm/llm/models/openrouter.py)
    adapters/ledger_hook.py      wraps LLMInterface.update_cost_and_token_usage → common ledger + cache
    tests/  runs/  pyproject.toml   (Python 3.11, pip -e upstream, pymoo, botorch)
  PAPER_TARGETS.md               the numbers we try to reproduce, each with its source (paper table / repo CSV)
  REPLICATION_REPORT.md          verdict per claim: reproduced / partial / not reproduced
```

**Reuse.** The record/replay key design follows `grid-path-challenge/harness/llm/replay.py` (`ReplayClient`). Prices and the qwen fix follow `harness_l2p/llm.py::PRICES` / `price_of`. The ledger pattern follows `experiments/x8_l2prime/x8_run.py::spent()` (re-price from tokens).

**What the shim does differently:**
- the ledger is checked **before** every call;
- there is a hard stop at each sub-cap;
- prices are true OpenRouter per-token rates (avoiding the $3/$15 fallback bug in `harness/llm/meter.py`);
- `OPENROUTER_API_KEY` is read from the existing GPC `.env`.

**Budget sub-caps ($25):**

| Item | Cap |
|---|---:|
| Chimera on GPT-4o | $10 |
| Chimera on qwen | $1.5 |
| MoHOLLM on Gemini Flash | $3 |
| MoHOLLM on qwen | $1 |
| Phase 3 adaptation | $3 |
| Phase 4 X9b | $4 |
| Reserve | $2.5 |

**Gate P0:**
1. Both uv envs install, and the upstream packages import.
2. `pytest -m offline` collects.
3. One OpenRouter ping per model (4 models) costs ≤ $0.01 total and is written to the ledger.
4. A replay of the same ping costs $0.

---

## Phase 1: offline module tests ($0)

Each test uses the papers' own use cases. Marker: `offline`; LLM calls are replaced by scripted fakes.

### Chimera (`sandbox/chimera/tests/`)

| Module (upstream) | Tests |
|---|---|
| `src/components.py::EcommerceSimulatorV5` | **Formula checks:** elasticity (p/100)^−1.2; ad response 1+0.3·ln(1+a/1000); seasonality floor 0.75; the trust rules (>+10% → ×0.98, <−5% → ×1.03, ad bonus, 0.2% decay); profit identity. **Dynamics check:** reproduce `results/preprint_results/ecom/environment/*.csv` from `preprint/environment_dynamics_analysis.py` under the same seeds (exact, or tolerance 1e-6). |
| `SymbolicGuardianV4` and `src/csl_guardian.py::CSLGuardianEcom` (`policies/ecommerce_guard.csl`) | **Property tests (hypothesis), 10k random actions:** after `repair_action`, `validate_action` is valid; repair is idempotent; repair is the identity on valid actions; CSL and legacy guardian agree. **TLA+:** run TLC on `TLA+_verification/MC.cfg` if Java and tla2tools are present; otherwise skip with a reason. |
| `CausalEngineV6` | **Data and fit:** regenerate training data with the fixed seed (500×50); fit `CausalForestDML`. **Effect quality:** the sign and magnitude of τ̂ for a grid of actions vs a **ground-truth MC effect**, computed from `simulate_plan`-style rollouts of the simulator (action vs no-op) — report rank correlation and bias. **SHAP:** additivity (SHAP sum + base = τ̂). **Bookkeeping:** `retrain` grows the data. |
| Agents (`preprint/three_agent_comparative_benchmark.py`: `create_llm_only_agent`, `create_llm_symbolic_agent`, `create_full_chimera_agent`, `run_agent_scenario`) | With `scripted_llm`: the tool-call loop runs, invalid hypotheses are regenerated, and the JSON output parses. A forced-failure test (scripted LLM proposes a price below cost) is repaired by the guardian. |

**Refactor needed (in `sandbox/chimera/adapters/`, upstream not edited).** Agent constructors are monkeypatched so `ChatOpenAI(model="gpt-4o", …)` is built through `adapters/llm.make_chat_llm`, which points at the OpenRouter base_url with cache and ledger. The runner script imports upstream modules and injects the factory.

### MoHOLLM (`sandbox/mohollm/tests/`)

| Module | Tests |
|---|---|
| `space_partitioning/kd_tree_partitioning.py` | Leaves are disjoint and cover the bounding box; every point lies in exactly one leaf. `adaptive_leafsize(t, d) == m0·d + ceil(λ·log1p t)`. Categorical dims are handled. |
| `region_acquisition_functions/score_region_acq_hv.py` | HV contribution equals brute force with pymoo HV. Probabilities are non-negative and sum to 1. α comes from each scheduler. The exploitation term is the max contribution per box (pins the code's behaviour documented in report 04 §6). |
| `acquisition_functions/hypervolume_improvement.py` | Top-k ordering matches brute-force HVI on toy fronts. |
| `utils/prompt_builder.py` + `prompt_templates/base/{partitioning,vanilla}` | The rendered prompt contains the box bounds and ICL examples. Snapshot test. |
| `llm/llm.py::to_json` | Robust to markdown fences, trailing text, bad JSON (fixture strings). |
| Benchmarks (`benchmarks/branin_currin.py`, `penicillin.py`, `vehicle_safety.py`, `car_side_impact.py`, ZDT/DTLZ via `benchmark_initialization.py`) | Evaluation matches reference values (BoTorch `test_functions` implementations at fixed points). |
| End-to-end | `main.py` on `configurations/Simple2D/mohollm-BraninCurrin.json` with **RANDOM sampler + a scripted LLM surrogate**: the loop finishes 13 trials, HV is monotone non-decreasing, and the stats JSON is written. |

**Gate P1:**
- All `offline` tests pass, or a failure is documented as an upstream bug in `REPLICATION_REPORT.md` with a minimal patch in `adapters/`; upstream stays pristine and is patched at import.
- Chimera's dynamics CSVs reproduce exactly. If not, every downstream Chimera number is suspect, and we stop Chimera at P1.
- **Get the paper targets.** Read the MoHOLLM paper's tables (arXiv 2601.13892 and the ICLR version) and the Chimera preprint, and write `PAPER_TARGETS.md`, so replication has fixed numeric targets rather than the unverified figures in the Exploration reports.

---

## Phase 2: paid replication (record mode, then replay to verify)

**Protocol (every run):**
1. **Pilot first:** Chimera runs 4 weeks, MoHOLLM runs 2 trials. Measure the real $/unit, project the full cost, and abort if the projection exceeds the sub-cap.
2. Run in record mode.
3. Replay from the cache: identical numbers at $0. This is the reproducibility check.
4. Run the paired stats (`experiments/lib/stats.py`).

### Chimera runs (`sandbox/chimera/runs/`)

| ID | What | Model / seeds | Target (repo CSV) |
|---|---|---|---|
| R-C1 | Environment dynamics | – | `environment/*.csv` (done in P1) |
| R-C2 | 3 agents × {volume, margin} bias × 52 weeks (`three_agent_comparative_benchmark`) | gpt-4o, **1 seed** (cost: about 52 × (1+4+7) calls × 2 biases ≈ 1.2k calls ≈ $10 projected; the pilot decides) | `three_agent_summary.csv` |
| R-C2q | Same as R-C2 plus the neutral bias | qwen3.7-flash, **3 seeds** | Is the ordering preserved? |
| R-C3 | Neutral 3-agent (`neutral_three_agent_benchmark`) | gpt-4o if budget remains, else qwen only | `neutral_architecture_summary.csv` |
| R-C4 | Trust-multiplier sweep (5 λ), Full Chimera | qwen, 1 seed | `sensitivity_summary.csv` |
| R-C5 (ours) | **Does the LLM matter?** (a) causal oracle + **deterministic argmax** over LLM hypotheses; (b) **scripted hypotheses** (balanced/aggressive/conservative grid) + guardian + causal argmax, no LLM | qwen + $0 | New; directly informs Phase 3 |

**Claims checked:**
1. LLM-only fails under bias: loss under volume, trust collapse under margin.
2. Guardian removes the failure.
3. Full > Guardian in profit, for every bias.
4. Variance: Full has the lowest weekly sd.

Ordering claims are tested across 3 qwen seeds, with a CI. GPT-4o (1 seed) is reported as a point estimate.

### MoHOLLM runs (`sandbox/mohollm/runs/`)

| ID | What | Model / seeds |
|---|---|---|
| R-M1 | MoHOLLM (`SpacePartitioningmohollm`, KD-tree + ScoreRegionHVC + LLM sampler + LLM surrogate) vs global LLM (`optimization_method: mohollm`, vanilla prompts) on the 7 core problems | gemini-2.0-flash, 3 seeds |
| R-M2 | Non-LLM baselines on the same problems: random, NSGA-II (pymoo), qLogEHVI (BoTorch `qLogEHVI_sampler`) | $0, 3 seeds |
| R-M3 | Ablations on Penicillin: no partition; uniform box choice; random sampler in box; GP/TabPFN surrogate instead of LLM (`configurations/Penicillin/MOHOLLM-*`) | gemini, 3 seeds |
| R-M4 | Transfer: MoHOLLM vs global on BraninCurrin, Penicillin, VehicleSafety | qwen3.7-flash, 3 seeds |

**Claims checked:**
1. MoHOLLM HV > global LLM on ≥ 5 of 7 problems (paired over seeds; sign-flip across problem × seed).
2. MoHOLLM is "on par" with NSGA-II and qLogEHVI: the median HV ratio CI includes 1, or the gap is within the paper's reported spread.
3. The ablation ordering matches the paper's table from `PAPER_TARGETS.md`.
4. Projected cost of about $2–3 (Gemini) and about $1 (qwen); the pilot confirms.

**Gate P2:** `REPLICATION_REPORT.md` gives a verdict per claim. The verdicts decide which Phase 3 modules are built:

| Verdict | Phase 3 consequence |
|---|---|
| Chimera claim 3 (causal value adds profit) reproduces, **and** R-C5 shows the deterministic argmax is ≥ the LLM pick | Build the deterministic-selection K-hypothesis module (3d). Otherwise build it as an ablation only. |
| MoHOLLM claim 1 reproduces on Gemini but **not** on qwen | The box proposer in Phase 3 uses a model-swap arm (qwen vs gemini) |
| MoHOLLM claim 1 does not reproduce | Phase 3 builds boxes for **coverage and token-saving only**, not for the LLM's search ability |

The exact allocator (3a–3c) is built in every case; it does not depend on either paper's LLM claims.

---

## Phase 3: adapt to our setup (`grid-path-challenge/harness_l2p/`, environment unchanged)

**Step 3.0: reconcile the metric definitions.** The call says about 0.88% lift and a 2.5% ceiling; X8 measured +0.16/+0.30% with an oracle bound of +1.27/+1.43%.
- Recompute both from cached results (`experiments/results/cache`, `x8_detail.py`) under each candidate definition: offtake vs L0, offtake vs baseline, iROAS, guardrails on/off.
- Write the mapping into `runtime_findings/results/x9_metric_reconcile.md`.
- **Gate 3.0:** one agreed definition is used for everything after.

**New modules.** Python 3.9 compatible (GPC venv; `scipy 1.13.1` already has `optimize.milp`/HiGHS and `linprog` marginals — no new deps).

| Module | Contents | Reuses |
|---|---|---|
| `options.py` | Per lever: enumerate the bid ladder from `diag.options`, budget steps (G6 limits), pause, hold. Each option is projected (Δspend, Δrev, Δincr via `iota_lookup`) and prefiltered against G0–G7 per option, giving `blocked(Gx)` / `clamped(Gx)` / ok. | `harness/tools/features.diagnose`, `sizing.project_candidates`, `precheck.precheck`, `gpc/guardrails` constants, `incrementality.iota_lookup` |
| `allocator.py` | MILP (`scipy.optimize.milp`): one option per lever (G0), the allowance row, the **G8 floor as a row**, an optional GoalSpec row set. LP relaxation (`linprog`, method highs) for duals and reduced costs. Forced-option re-solve for the top unchosen options. | – |
| `ot.py` | Sinkhorn with fixed SKU/city marginals plus a Frank–Wolfe outer loop (2–3 passes, duality-gap stop) | numpy |
| `record.py` | Decision record (schema in report 05 §4): every option ends in a terminal state; factor decomposition (Δimpr × CTR×CVR × ASP × ι); duals; plan contrasts | – |
| `hypotheses.py` | Chimera-style K = 3 plans in one structured call (prompt `L2PP_hyp.v1.md`). Each plan becomes option restrictions/bonuses, gets a MILP solve, and the argmax under constraints is shipped. | `planner.py` call path, `harness.leaves.run.leaf`, `PricedMeter`, replay |
| `boxes.py` | MoHOLLM-style box scorer over SKU × city × keyword type (projected HV/value + coverage + UCB-V), choosing the top-M boxes for the LLM. Rules and random proposers for ablation. | `rules_planner.py`, `experiments/lib/scripted_l2p.py` (`RandomPlanner`) |
| `priors.py` | Typed, bounded adjustments to projection inputs, with evidence refs. Each one is ablated inside the record. | `intents.py` patterns |
| `goals.py` | `GoalSpec` pydantic schema + LLM goal compiler (`L2PP_goal.v1.md`) + feasibility check / minimal-relaxation report | `intents.py`, `validate_and_clip` |
| `policy_l2pp.py` | `L2PPHarness(Policy)`, modes `exact` / `exact_ot` / `hyp` / `priors` / `boxes`. Fail-soft to the L0 actions (same pattern as `L2PHarness`). Trace adds `decision_record`. | `harness_l2p/policy.py` |

**Tests** (`tests/harness_l2p/`, $0, Python 3.9):
- **`test_options.py`:** per-option prefilter parity with `gpc.guardrails.apply_guardrails`. Every option blocked by the prefilter is blocked by the engine and vice versa, over seed 7 runs 1–3 (existing `observations` fixture).
- **`test_allocator.py`:**
  - the MILP optimum equals brute force on random tiny instances (≤ 6 levers × 3 options);
  - the floor row holds; the solver gap is 0;
  - reduced-cost signs are right;
  - the forced-option re-solve is never better than the optimum.
- **`test_ot.py`:** marginals are satisfied to 1e-6; the FW gap does not increase; ε → 0 approaches the exact OT (compare with `linprog`).
- **`test_record.py`:** completeness = 1.0 (every option has a terminal state); the decomposition reproduces the projection within 1e-6; JSON schema validation.
- **`test_goals.py`:** schema clip/drop; infeasible goals produce a relaxation set; provenance is required.
- **`test_policy_l2pp.py`:** `FAULT_INJECT=*` gives exactly L0's actions; `exact` with an empty option set gives no-op; the engine `apply_guardrails` never blocks anything `exact` ships (except G8 on realized values) — a hard assertion.
- **AST isolation:** extend `tests/harness_l2p/test_rules.py` to the new modules (no `gpc.market`, `.truth`, `experiments`).
- **Regression:** existing `pytest tests -m "not slow"` still passes.

**Experiment X9a** (`experiments/x9_l2dprime/x9_run.py`, mirroring `x8_run.py`: `run`/`report`, `--arms --worlds --jobs --cap`; worlds `dev6` + `pert3`; ledger → programme ledger).

| Arm | Cost |
|---|---|
| `l0`, `l2p_native_r2` (cached), `oracle` | $0 |
| `l2pp_exact` | $0 |
| `l2pp_exact_noguard` (G3–G7 off — price of safety) | $0 |
| `l2pp_hyp` / `_hyp_rules` / `_hyp_random` (+ gemini swap if P2 says so) | ≈ $1.5 |
| `l2pp_priors` | ≈ $0.5 |
| `l2pp_boxes` | ≈ $1 |

LLM arms run 3 replicates. Metrics: those in report 05 §7, plus the model–market gap per shipped action.

| Gate | When | Condition | Decision |
|---|---|---|---|
| **3A** | after the $0 arms, before any paid call | Compare `l2pp_exact` to `l2p_native_r2` | If exact wins (paired p < 0.05), allocation moves out of the LLM. If exact loses or ties, the projection model is the bottleneck: fix the X3.1 slot-1 assumption and the share curve **before** any LLM arm. |
| **3B** | after the paid arms | Compare each LLM arm to its rules/random twin | Must be separable at p < 0.05 to be kept |
| **3C** | throughout | Floor met on every arm; record completeness = 1.0 | – |

---

## Phase 4: extend the grid environment for the new use cases (`grid-path-challenge/gpc/`)

**Back-compat rule:** every addition is **off by default**. A golden test pins current `dev` scores (all `l0`/`baseline` results for seeds 7/11/23/42/101/202 byte-identical) before and after Phase 4.

| # | Change | Files | Use case it enables |
|---|---|---|---|
| 4a | Add a public `region` column to cities (North: DEL; West: MUM, PUN; South: BLR, HYD); optional per-region aggregate rules **G9_REGION** (spend floor/cap, region ROAS floor), configured by the goal file | `gpc/world.py::_cities`, `gpc/guardrails.py` (new G9 block after G8; skipped when no goal file) | Aggregate guardrails vs cell decisions (the call's "North = 100+ cells") |
| 4b | **Goal files** `gpc/goals/*.json` (GoalSpec): `G_macro` (portfolio offtake +X% at floor R, budget B); `G_sku_push` (sub-category +20%); `G_launch_sov` (launch SKU, North SOV ≥ target); `G_hetero` (offtake and SOV, Pareto); `G_infeasible`. Exposed on `Observation.goal` (public); scored by `score.py`. | `gpc/observation.py`, `gpc/runner.py` (`--goal`), `gpc/score.py` (`goal_attainment`, `sov`, per-region metrics) | Persona goals, macro vs micro, homogeneous vs heterogeneous |
| 4c | **SOV metric**: own impressions ÷ total auction impressions per keyword × city (the market already draws a competitor level z per auction in `market.py::_slot_shares`; expose the totals in `daily_facts` as a new column, default-off in the outputs) | `gpc/market.py`, `gpc/runner.py` | Launch-SOV goals |
| 4d | **Fixed-totals scenario** (SKU and city budget marginals) for OT | `gpc/goals/G_totals.json`, plus a guardrail row in G9 | The OT framing |
| 4e | **Launch scenario**: one SKU with a short history (launch age a few days, reduced warm-up data) via a scenario variant | `experiments/lib/scenarios.py::VARIANTS` (`V_launch`), `gpc/world.py::_products` launch-age override from the scenario | Cold-start launch + SOV |
| 4f | **Guardrail-relaxed mode** for ceiling measurement only (`GPC_GUARDRAILS=relaxed` turns off G3–G7; refused unless the env var is set; never available to the eval) | `gpc/guardrails.py` | Price of safety vs the 2.5% ceiling |
| 4g | **Goal-aware oracle bound** (offline): the exact allocator run on **true** response curves, giving the ceiling per goal | `experiments/lib/oracle.py` (new `goal_oracle`) | Share-of-ceiling per goal |
| 4h | Viewer panel for the decision record (optional, last) | `viewer/` | Explainability demo |

**Tests:**
- **`tests/test_env_goals.py`:**
  - golden back-compat (dev scores unchanged with no goal file);
  - G9 blocks/clamps exactly at the rule edges;
  - goal files validate against the GoalSpec schema (shared with `harness_l2p/goals.py`);
  - SOV is in [0, 1] and equals 1 when the competitor draw is forced to 0;
  - the launch variant builds and the warm-up shortening is honoured;
  - relaxed mode raises an error unless the env var is set;
  - `goal_oracle` ≥ every arm on every goal (a bound sanity check).
- The existing `tests/test_sandbox.py` and harness tests stay green.
- AST isolation: `Observation.goal` is public; `goal_oracle` stays in `experiments/` only.

**Experiment X9b** (same runner, new `--goals` axis):
- **Grid:** the goals {macro, sku_push, launch_sov, hetero, totals, infeasible} × worlds dev6 (+ `V_launch` for launch_sov).
- **Arms:** l0, l2p_native_r2, l2pp_exact(_ot), and the best LLM arm from 3B, with 3 replicates.

**Metrics:**
- goal attainment and share of the goal-oracle ceiling;
- Pareto front and hypervolume for `hetero`;
- for `infeasible`: the relaxation report matches a brute-force check;
- record completeness and model–market gap;
- $/run.

**Final confirmation:** the best arm runs once on fresh seeds 3001–3006 (as previously reserved).

**Gate 4:** golden back-compat green, every goal scenario runs end to end for every arm, and the confirmation result is reported as it comes out (pass or fail).

---

## Documents produced

- `sandbox/REPLICATION_REPORT.md` (+ an artifact)
- `runtime_findings/results/x9_l2dprime.md`
- updates to `explore-and-understand/03–05`, replacing unverified numbers with the replicated ones
- an X9 section in `system_design_proposals/03_l2prime_expressiveness_and_scale.md`

---

## Verification (end to end)

1. **Phase 0:** `cd sandbox/chimera && uv run pytest -m offline -q`, and the same for `sandbox/mohollm`. Ping script: ledger line written; replay costs $0.
2. **Phase 1:** all `offline` tests green; Chimera environment CSVs match; `PAPER_TARGETS.md` filled from the paper tables.
3. **Phase 2:**
   - `uv run python runs/r_c2.py --pilot` → projection → full run → `--replay` gives identical CSVs.
   - MoHOLLM: `runs/r_m1.py --pilot` → full → replay.
   - `REPLICATION_REPORT.md` verdicts, with CIs.
4. **Phase 3:**
   - `cd grid-path-challenge && PYTHONPATH=. .venv/bin/python -m pytest tests -m "not slow" -q`;
   - `PYTHONPATH=.:.. .venv/bin/python -m experiments.x9_l2dprime.x9_run run --arms l0,l2pp_exact,l2pp_exact_noguard --worlds dev6`, then `report` — gate 3A;
   - then the paid arms, with replay verification.
5. **Phase 4:** golden test; `make score POLICY=harness_l2p.policy_l2pp:L2PPHarness` with no goal file equals the X9a `exact` numbers; X9b run + report; mermaid check and artifact publish for the reports.
6. **Ledger:** `sandbox/ledger.jsonl` total ≤ $25 with per-phase sub-totals printed by `common/ledger.py --summary`.
