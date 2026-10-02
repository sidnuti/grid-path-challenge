# Plan: System 1 harness (ProcLLM + HTN) for the Grid Path Challenge, with System 2 hooks

## Context

We chose Approach A (`problem-mapped/A-procllm-htn-harness.md`) as the backbone. This plan turns it into working code, tests and an evaluation suite inside `grid-path-challenge/`.

Arnab's notebook and the "three systems" note set the long-term shape:

- **System 1 (Type-1, real-time):** a fixed-depth, data-informed procedural chain that reacts to events and campaign feedback ("what do I do now?" at T, T+5 min, T+1 h, T+3 h). **← built now**, triggered weekly for the challenge.
- **System 2 (Type-2, offline cron):** a feedback learner over playbook arms (R1…R4) with reasoning depth L0/L1/L2 (market, brand and LLM reasoning). Rewards come from campaign success (implicit) and human chat feedback. It consumes System 1 traces and updates System 1 params. **← hooks only now** (trace schema, params file, arm registry, reward, learner stub).
- **System 3:** persona/brand-specific evolving workflows (agents-as-code, ADAS; vanilla vs C1/C2/C3; alerts, alarms, highlights, adaptive insights). **← design note only.**

Decisions already made:
- Scope: S1 plus S2 hooks.
- Code lives in `grid-path-challenge/harness/`.
- LLM provider: **OpenRouter by default**, with Anthropic and OpenAI adapters selected through `.env`.
- Never modify `gpc/market.py`, `gpc/guardrails.py`, `gpc/runner.py` or `gpc/score.py`.

## Data evidence that drives the scenarios (dev, from `data/` — the baseline's own trajectory)

| ID | Evidence | Harness behaviour it tests |
|---|---|---|
| E1 | Organic units displaced per ad order (regression): brand −0.88, generic −0.50, competitor ≈ 0. Per SKU: brand −0.68…−1.13, generic −0.37…−0.76 | Incrementality estimator. Its ordering must hold across seeds |
| E2 | **98% of warm-up spend (₹18.6K of ₹18.9K/day) is in contested markets.** K03 "soap": 3 siblings in every city, slot-1 share 0.33–0.90. DEL K01: S3 holds slot 1 95% of the time while 4 siblings sit at 13–36% | Sibling arbitration (SG3) |
| E3 | 6 campaigns ran out on **all 28** warm-up days (C-S1-BLR, C-S5-DEL, C-S5-BLR, C-S2-MUM, C-S3-BLR, C-S1-DEL). Run-outs happen in the evening/afternoon | Budget method (SG4) |
| E4 | Demand surge: K07/K08 in BLR from week 4 (+27–65%); in DEL from week 6 (K08 ×2.06). K04 rising late | Shock detection lead time (SG5) |
| E5 | MUM K05/K06 reach +25–42% in weeks 4–6, then 0.6–0.7× from week 7. **Confounded with the baseline's own bid cuts** | Shock attribution (L2): demand vs own-action |
| E6 | HYD K05 CPM +10–12% from week 6 while reach is +32% | Ambiguous price vs demand signal |
| E7 | S2-HYD on-shelf availability 0.42 on days 42–48 | No increases during the dip; no post-dip cuts |
| E8 | S3 generic displacement −0.76 vs −0.37…−0.44 for other SKUs. S3 ranks organically 3–4 on K03/K04 | Using organic rank as a prior for incrementality |
| E9 | Baseline ends at 4.97× vs a 4.54× floor; spend falls from ₹18.9K to ₹17.8K/day | Headroom ledger and allowance |
| E10 | 27 top-slot (G3) blocks in the baseline | Pre-checks; blocked share ≤ 5% |

Caveat, repeated in the docs: these are dev specifics, and the reach series are confounded by the baseline's own actions. Scenario tests therefore assert *behaviours* on constructed observations and on perturbed worlds, never dev magnitudes.

## Code layout (new; `gpc/` untouched)

```
grid-path-challenge/
  harness/
    policy.py            HTNHarness(Policy) [full]; HTNToolsOnly (llm=None, the ablation arm)
    config.py            Params dataclass ← harness/params/default.json (S2-tunable), PARAMS_PATH env override
    htn/tasks.py         Task, Method, TaskGraph; fixed depth ≤3; per-occurrence `decomposed` flag (fixes the
                         ProcLLM UpdateTask loop); preconditions + numeric effects; trigger types (scheduled|event)
    htn/methods.py       M_Reprice(SG2) M_Sibling(SG3) M_Budget(SG4) M_Shock(SG5) M_Explore(SG6) M_Base M_Final(SG7/S10)
    tools/features.py    reuse gpc.engine.grid.build_grid/predict_cell, gpc.engine.loop.cell_verdicts/campaign_pacing,
                         gpc.engine.traversal.choose_bids (bid options)
    tools/incrementality.py  numpy lstsq: organic ~ FE(sku×city)+dow+Σ_type β·ad_orders; sku×type shrunk to type;
                         organic_rank≤3 prior; returns ι, SE per type/cell
    tools/shocks.py      z-scores (last 7d vs prior 21d) of slot-1-equiv reach, CPM, OSA; excludes run-out-truncated
                         dayparts; flags own-action confounding (bid changed in window)
    tools/siblings.py    market = city×keyword; siblings, slot-1 share, leader score = conv×relevance×ι
    tools/headroom.py    dROAS-to-date, H_t, allowance schedule (params), run-6 full spend minus margin
    tools/sizing.py      scipy linprog (same pattern as traversal.py transport LP): max Σι·Δrev s.t. headroom allowance
    tools/precheck.py    predicts G0/G3/G4/G5/G7 outcomes using constants imported from gpc.guardrails
    tools/verify.py      schema + guardrail dry-run via gpc.guardrails.apply_guardrails (read-only; mirrored
                         precheck fallback if Gobblecube says no) + floor×(1+margin) + caps; ≤1 repair (halve increases)
    leaves/schemas.py    pydantic v2 models for L1–L6 outputs; validate_and_clip; unknown IDs dropped
    leaves/prompts/*.md  versioned L1 value, L2 shock, L3 sibling, L4 explore, L5 ledger, L6 review (veto-only)
    leaves/run.py        leaf(llm, name, ctx, default): narrow ctx → JSON → validate → default on any failure
    llm/client.py        LLMClient protocol: complete_json(system, user, schema, timeout) → (dict, Usage)
    llm/providers.py     OpenRouter (openai SDK, base_url=https://openrouter.ai/api/v1), OpenAI (openai SDK),
                         Anthropic (anthropic SDK); lazy imports; chosen by .env LLM_PROVIDER; per-leaf model
                         override LLM_MODEL_L1… ; JSON-mode + one repair retry
    llm/replay.py        cache keyed sha256(prompt_ver, leaf, ctx, schema_ver, replicate); LLM_MODE=off|record|replay|live
    llm/meter.py         calls, tokens, $ (price table in params), wall-clock; BudgetExceeded per run
    llm/faults.py        FAULT_INJECT=timeout|malformed|out_of_range|budget|exception
    memory/ledger.py     hypothesis claims {unit, claim, predicted, realised, status}; realised measured from obs only
    trace/schema.py      RunTrace (JSONL per run): obs digest, flags, leaf I/O, candidates, sizing, verify, actions,
                         meter, params version, fallback reason  ← System-2 input
    trace/writer.py      TRACE_DIR env; default off during `make score`
    s2/arms.py           ArmRegistry: named Params overrides (headroom front/back-load, shock z 2.0/2.5/3.0,
                         explore on/off, depth L0/L1/L2 per unit type)
    s2/reward.py         reward(SimResult, baseline SimResult): paired lift, floor gate, $ cost, P(lift<0)
    s2/learner_stub.py   interface propose_params(traces, rewards) → Params; stub = best mean arm; CLI for cron
  harness_eval/          offline tooling; NEVER imported by harness/ (enforced by test)
    worlds.py            world sets: dev seeds {7,11,23,42} search, {101,202} held-out; perturbed scenarios
                         P1–P6 generated from our own template (moved shock run/city/kw/kind, shifted response
                         levels) → harness_eval/scenarios/*.json (pending Gobblecube OK)
    run_matrix.py        arms × worlds × replicates using gpc.runner.simulate (CRN, paired deltas) → CSV + report.md
    probes.py            E1–E10 probes on data/ and on harness traces
  tests/harness/         (see Tests)
  .env.example           LLM_PROVIDER, OPENROUTER_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, LLM_MODEL*, LLM_MODE,
                         LLM_MAX_USD_PER_RUN, TRACE_DIR, FAULT_INJECT
```

Edits to existing repo files: add `openai`, `anthropic`, `python-dotenv` and `pydantic>=2` to `requirements.txt`; add `.env`, `harness_eval/out/` and `llm_cache/` (except committed replay sets) to `.gitignore`; add Makefile targets `harness-test`, `harness-eval` and `probes`. `make score POLICY=harness.policy:HTNHarness` works unchanged.

## Runtime chain (fixed depth; one trigger = one run)

T1 Diagnose (tools) → flag units → T2/T3 leaves L1–L5 (parallel; city-batched) → T4 methods produce candidate moves (one per lever, pre-checked) → T5 sizing LP → L6 veto-only review → T6 verify (≤1 repair) → T7 emit actions, ledger and trace.

Fail-soft operates at three levels:
1. A leaf failure returns that leaf's default.
2. A verify failure after the repair falls back to baseline actions.
3. Any exception or budget breach falls back to `DeterministicTraversal().recommend(obs)`.

Depth is controlled by params:
- **L0** = tools-only;
- **L1** = + leaves;
- **L2** = + review and debate for large moves.

## Tests (`tests/harness/`, pytest; `-m slow` for simulations)

- **Rules:** AST scan of `harness/` for `gpc.market`, `gpc.scenarios`, `gpc.world` truth, `.truth`, `harness_eval` and file opens under `gpc/scenarios`. Rendered prompts on a dev observation must contain no scenario-file numbers (the test loads dev.json; the harness never does).
- **Tools:**
  - The incrementality estimator recovers known coefficients on synthetic data and the brand < generic < competitor ordering on dev and seeds.
  - Shocks: an injected surge or CPM jump is flagged, and no false flags appear on a stationary synthetic series.
  - Siblings: 40/50 contested markets on the dev public tables.
  - Headroom arithmetic is correct.
  - The LP never exceeds its allowance.
  - Precheck: predicted blocks match `apply_guardrails` on randomized action sets (property test).
- **HTN:** termination with no re-expansion; preconditions skip methods; depth ≤ 3; one action per lever.
- **Leaves:**
  - Malformed JSON, out-of-range values, unknown IDs and timeouts each produce the default or a clipped value.
  - The schema version is stamped.
- **LLM layer:** provider selection from `.env`; replay determinism (same cache → identical actions); meter budget enforcement; tests use MockLLM only, so no network calls.
- **Fail-soft:** each `FAULT_INJECT` mode makes `simulate(n_runs=2)` complete with baseline actions, and the trace records the reason.
- **Scenarios S1–S10** on constructed observations:
  - S1: no raise on a slot-1 brand cell.
  - S2: a competitor miss is cut ≥ 20% at once and redeployed.
  - S3: followers step down and the leader holds.
  - S4: a budget raise is valid under G5/G7 after trimming a weak keyword.
  - S5: a surge gives raises on clearing cells.
  - S6: no increases during low OSA, and dip days are masked.
  - S7: capped exploration.
  - S8: retreat on a price shock.
  - S9: baseline fallback on LLM failure.
  - S10: run 6 uses the full allowance minus the margin.
- **Slow regression:** tools-only and full (replay) meet the floor on dev seed 7. The blocked share is ≤ 10%, and the action count is ≤ the cap.

## Evaluation matrix (`harness_eval/run_matrix.py`)

- **Arms:** baseline, A1 tools-only, A2 full, A3 leave-one-out (L1…L6), S2 arms.
- **Worlds:** search seeds + held-out seeds + P1–P6.
- **Replicates:** 3 LLM replicates (record once, then replay).
- **Metrics:**
  - paired offtake lift %, floor met, realised dROAS, spend/day;
  - proposed / shipped / blocked share, P(lift < 0);
  - $/run, tokens, calls, wall-clock, fallback count.
- **Outputs:** `report.md` with lift-vs-cost and ablation tables, which feed the cost memo.
- **LLM budget:** ≈ $40 of the $150 (A2 + LOO records on Sonnet-class via OpenRouter). Tools-only arms are free.

## Docs to add in `problem-mapped/`

- `A1-implementation.md`: architecture, module map, task graph, leaf contracts, provider/.env setup, fail-soft, trace schema.
- `A2-tests-and-scenarios.md`: test catalogue, S1–S10 specs with pass criteria, evaluation matrix, ablation protocol.
- `A3-data-evidence.md`: E1–E10 with the probe outputs and the confounding caveats.
- `systems-1-2-3-roadmap.md`: how S1 traces feed S2 (arms, reward, cron learner) and how S2 updates S1 params; the S3 persona-workflow sketch; the T / T+5m / T+1h / T+3h trigger model.

## Milestones

1. **M0:** scaffold, config, `.env` handling, rules tests.
2. **M1:** tools + `HTNToolsOnly`. Gate: floor met and ≥ baseline on dev + 4 seeds (no LLM).
3. **M2:** LLM layer, leaves, replay, meter, faults, fail-soft tests.
4. **M3:** methods wired with the LLM; scenario tests S1–S10.
5. **M4:** `harness_eval` + probes + first matrix run.
6. **M5:** trace + S2 hooks.
7. **M6:** docs.

## Verification

- `make setup && make test && make harness-test`: existing sandbox tests still pass and the new unit/scenario tests pass, with no network.
- `make score POLICY=harness.policy:HTNToolsOnly`: floor met; lift vs baseline reported.
- `LLM_MODE=replay make score POLICY=harness.policy:HTNHarness`: reproducible numbers, identical across reruns.
- `FAULT_INJECT=timeout make run POLICY=harness.policy:HTNHarness`: completes; the trace shows the fallback.
- `make harness-eval`: matrix report with paired lift, floor, ablation and cost per run.
- `git diff --stat gpc/market.py gpc/guardrails.py gpc/runner.py gpc/score.py` is empty.

## Open items to confirm with Gobblecube (do not block the build)

- Is a read-only `apply_guardrails` dry-run allowed? A mirrored precheck is ready as the fallback.
- Is a committed replay cache acceptable for reproducibility?
- Are self-authored perturbed scenarios acceptable for offline validation?
