# A1 — Implementation: the System 1 harness (ProcLLM + HTN)

Companion to `A-procllm-htn-harness.md` (the approach report) and the plan/handoff in
`plan_copies/`. This document tracks what was actually built; `logs/2026-10-02-build-log.md` has
the session-by-session narrative (bugs hit, decisions made, test results).

## Status

- **M0 scaffold** — done.
- **M1 tools + `HTNToolsOnly`** — done, gate passed (floor met + lift >= baseline on dev seeds
  7/11/23/42, zero guardrail-blocked proposals).
- **M2 LLM layer** — done: `harness/llm/*` (client, providers, replay, meter, faults) and
  `harness/leaves/{schemas,run}.py`, 30 tests (MockLLM only, no network), plus one live
  OpenRouter smoke test outside pytest confirming the configured key/model work end to end.
- **M3 leaves wired into methods** — done: `harness/htn/llm_methods.py`, leaf prompts
  (`harness/leaves/prompts/*.v1.md`), `tools/shocks.py`, S1-S10 scenario tests (11/11 passing).
  `HTNHarness` now genuinely differs from `HTNToolsOnly` when `params.depth != "L0"` and an LLM is
  configured; with no LLM configured (the default) it is still provably identical — see below.
- **M4 `harness_eval`** — done: `worlds.py` (search/held-out seeds + 6 perturbed scenarios),
  `run_matrix.py` (arms x worlds x replicates, cost-free by default), `probes.py` (E1/E2/E3/E9/E10
  re-derived from `data/`, closely matching the original hand-written evidence table — see below).
  First real numbers: `tools_only` beats baseline by +0.88% on a held-out seed never touched while
  building anything, not just the search seeds the M1 gate used.
- **M5 trace + S2 hooks** — done: `harness/trace/{schema,writer}.py` (`RunTrace`, JSONL, off by
  default via `TRACE_DIR`), `harness/s2/{arms,reward,learner_stub}.py` (named `Params` overrides,
  paired/aggregate reward with a floor gate, a "best qualifying arm" stub + CLI).
- **M6 docs** — done: this doc, `A2-tests-and-scenarios.md`, `A3-data-evidence.md`,
  `systems-1-2-3-roadmap.md`, and the sibling-cost wording fix in
  `00-problem-map-and-recommendation.md` (SG3 row).
- All six milestones from the approved plan are now done. Remaining open items are listed at the
  bottom of this doc, not a milestone list.

## Architecture (as built, M0+M1)

```
grid-path-challenge/
  harness/
    config.py                 Params dataclass <- harness/params/default.json, PARAMS_PATH override
    policy.py                 HTNToolsOnly (L0, no LLM); HTNHarness (currently == HTNToolsOnly,
                               pending M2/M3's LLM leaves)
    htn/
      tasks.py                Task/Method/MethodRegistry scaffold (depth enforced structurally:
                               diagnose -> methods -> sizing/precheck is the whole tree, no re-expansion)
      methods.py               M_Reprice (SG2), M_Sibling (SG3, hold-set only), M_Budget (SG4),
                               M_CompetitorCut, M_Base (defers to gpc.engine.traversal's own ladder cut)
    tools/
      features.py              diagnose(obs) -> grid/verdicts/pacing/bids/options (wraps gpc.engine)
      incrementality.py        organic_units ~ FE(sku x city) + FE(dow) + beta_type * ad_orders_type,
                                per-SKU betas shrunk toward the pooled type beta
      siblings.py               city x keyword markets; leader_score = conv1 x ASP x iota;
                                followers_to_hold() for SG3
      headroom.py               window-cumulative ROAS floor -> a per-run spend allowance
      sizing.py                 Lagrangian knapsack over raise candidates, bounded by the allowance
      precheck.py               mirrors G0/G3/G4/G5/G7 using gpc.guardrails' own constants
    llm/
      client.py                 LLMClient protocol + Usage dataclass
      providers.py               OpenRouter/OpenAI (shared openai-SDK base) + Anthropic adapters;
                                 lazy imports; build_provider() routes on LLM_PROVIDER/LLM_MODEL
      meter.py                   Meter: cost/token/call/wall-clock tracking, BudgetExceeded
      replay.py                  ReplayClient: off|record|replay|live, sha256-keyed cache
      faults.py                  FaultInjectingClient: FAULT_INJECT=timeout|exception|malformed|
                                 out_of_range|budget
      __init__.py                build_llm_stack(params): .env -> provider -> faults -> meter ->
                                 replay, the one client a leaf is handed
    leaves/
      schemas.py                 pydantic v2 L1Value/L2Shock/L3Sibling/L4Explore/L5Ledger/L6Review;
                                 validate_and_clip() (clips in range, defaults on hard failure or
                                 an unknown id)
      run.py                     leaf(llm, name, system, user, schema_cls, default, ...): the one
                                 call site a method uses; llm=None -> default, no call
      render.py                   loads prompts/<name>.v<ver>.md (system/user split), str.format
                                 renders the user half
      prompts/*.v1.md             L1_value, L2_shock, L3_sibling, L4_explore, L6_review
    htn/
      llm_methods.py               sibling_tiebreak (L3), shock_raises (L2), adjust_raise_sizes
                                 (L1), explore_candidates (L4), review_veto (L6, depth L2 only)
    trace/
      schema.py                    RunTrace dataclass; build_trace() reshapes policy.last_trace
                                 into it; obs_digest hashes campaigns/campaign_keywords/recent facts
      writer.py                    maybe_write_trace() (no-op unless TRACE_DIR is set),
                                 read_traces() (JSONL -> list[RunTrace])
    s2/
      arms.py                      Arm, ArmRegistry, DEFAULT_ARMS (headroom front/back-load,
                                 shock-z 2.0/2.5/3.0, explore on/off, depth L0/L1/L2)
      reward.py                     pair_reward, aggregate_reward (score=None if any world misses
                                 the floor)
      learner_stub.py                propose_params (best qualifying arm) + CLI for cron
  harness_eval/                    offline tooling; never imported by harness/ (test_rules.py checks)
    worlds.py                      SEARCH_SEEDS/HELDOUT_SEEDS + P1-P6 perturbed scenarios
    run_matrix.py                   arms x worlds x replicates -> out/{matrix.csv,report.md};
                                  LLM arms gated on LLM_MODE != "off"
    probes.py                       E1/E2/E3/E9/E10 (+ a per-run E4/E5 shock-recall scan) from data/
    scenarios/*.json                 P1-P6, generated by worlds.py (gitignored would be reasonable;
                                  currently regenerated on demand, not committed)
    out/                             matrix.csv, report.md, probes.json (gitignored)
  tests/harness/
    test_rules.py               AST scan: no gpc.market/gpc.scenarios/harness_eval imports, no
                                `.truth` access, no gpc/scenarios file opens
    test_tools.py                incrementality synthetic recovery + dev ordering, siblings 40/50,
                                headroom non-negativity, precheck-vs-apply_guardrails property test
    test_tools_only_policy.py    (marked slow) floor-met + no-fallback + blocked-share gate,
                                parametrized over seeds 7/11/23/42
    test_llm.py                  provider routing, replay determinism, meter budget, fault modes
    test_leaves.py                schema validate/clip, leaf() under each fault mode
    test_scenarios.py            S1-S10, on the dev warm-up fixture and targeted perturbations of it
    test_trace.py                 TRACE_DIR on/off, build_trace field counts, JSONL round-trip
    test_s2.py                    ArmRegistry, aggregate_reward's floor gate, propose_params
  test_harness_eval.py            (flat, not tests/harness_eval/ — avoids the M0 name-collision
                                 lesson) world/arm selection, LeafAblationLLM, one real run_matrix call
pytest.ini                       registers the `slow` marker
.env                              gitignored; holds the user's OpenRouter key + LLM_MODEL
```

**All six plan milestones (M0-M6) are now built.** 99 fast tests + 8 slow tests, all passing.

## How `HTNToolsOnly.recommend(obs)` works

1. `diagnose(obs)` — reuses `gpc.engine.{grid,loop,traversal}` to get the grid, cell verdicts,
   campaign pacing, and the engine's own chosen bid per cell (`choose_bids`).
2. `iota_lookup(obs)` — fits the incrementality regression and returns a `(sku_id,
   keyword_type) -> iota` lookup.
3. `m_sibling_holds` — the set of (campaign_id, keyword_id) that must not be raised because a
   sibling already holds >=80% of slot 1 on that city x keyword market.
4. Candidate raises: `m_reprice_raises` (CLEARS cells, not held, raised toward the engine's own
   chosen option) + `m_budget_raises` (campaigns that ran out >= 2 of the last 7 days and clear
   goal on spend-weighted ROAS). Both get `pred_delta_spend`/`pred_delta_rev` from
   `gpc.guardrails.project_actions` (read-only import — the same projection G8 will use).
5. `compute_headroom(obs, params)` turns the window-cumulative ROAS floor into this run's spend
   allowance; `select_raises` picks which raises to ship via the Lagrangian knapsack, bounded by
   that allowance.
6. Candidate cuts: `m_competitor_cuts` (MISSES + keyword_type == competition: cut immediately,
   skipping the patience ladder, since ~0 incrementality means ~0 offtake cost) and `m_base_cuts`
   (everything else that misses goal: defers to the engine's own ladder-paced cut).
7. `filter_precheck` drops anything G0/G3/G4/G5/G7 would block before it is even proposed.
8. The survivors become the returned actions DataFrame; `gpc.guardrails.apply_guardrails` (run by
   `gpc.runner`, outside the policy) has the final say — in particular G8's portfolio floor trim,
   which this harness never tries to pre-empt.

Fail-soft: `HTNToolsOnly.recommend` catches any exception and falls back to
`gpc.policy.DeterministicTraversal().recommend(obs)`, recording `fallback_reason` in
`self.last_trace`. Two bugs that triggered this during development (an un-indexed `pacing` frame
passed into `project_actions`, and a non-vectorized `max()` inside a pandas `.assign()`) are
recorded in the build log — both are fixed, and no seed/run fell back in the M1 gate run.

## How `HTNHarness.recommend(obs)` differs (M3, depth L1/L2 with an LLM configured)

`_harness_recommend` is the `HTNToolsOnly` pipeline above with five insertions, every one of them
a no-op when `llm is None` (so `HTNHarness(llm=None)` runs `_tools_only_recommend` directly — not
merely producing the same output, the same function call):

1. `sibling_tiebreak` — before `m_sibling_holds` finalises the hold set, re-checks every
   contested market's leader; only a near-tie (top two `leader_score` within 10%) goes to L3.
2. `adjust_raise_sizes` — tier-B `m_reprice_raises` candidates get their raise size scaled by
   L1's `bid_multiplier` (0.5-1.5); tier A and C are untouched.
3. `shock_raises` (new, via `tools/shocks.py`'s z-scores) — a confirmed, non-confounded demand
   surge becomes an extra raise candidate even on a cell whose mechanical verdict hasn't caught
   up yet.
4. `review_veto` — L2 depth only: one pass over this run's raises above
   `params.llm_review_threshold_inr`, which can drop all of them (not selectively) if L6 vetoes.
5. `explore_candidates` — capped, leaf-gated small raises on THIN cells; disabled by default
   (`explore_enabled: false`).

`HTNHarness` keeps its own `(campaign_id, keyword_id) -> [day, ...]` log of bid/budget changes it
has proposed, across runs within one `simulate()` call, and feeds it to `detect_shocks` as
`own_action_days` — this is how E5's confounding (a reach swing that is really the harness's own
last move landing, not a market shock) gets flagged without guessing at it from the data alone.

Verified, not just asserted: ran `HTNToolsOnly` and `HTNHarness(llm=None)` on the same world for 2
runs and diffed `gpc.score.summarize()` output — identical. Ran `HTNHarness(depth="L1",
llm=MockLLM(...))` end to end through `simulate()`, once with neutral mock answers (identical
output to tools-only again) and once with the mock forced to answer "yes" to every judgment,
producing real `M_Explore`/shock-raise actions that passed through sizing, precheck and
`apply_guardrails` without error.

## Deviations from the plan

- **Sizing.** The plan's `scipy.optimize.linprog` transport step is replaced (per the handoff's
  decision, carried into code) by a Lagrangian multiple-choice knapsack over *raise* candidates
  only; cuts are unconditional, handled directly by the methods. The exact objective used here —
  `iota * delta_rev - mu * delta_spend`, standard knapsack form — is a simplification of the
  handoff note's `iota * delta_rev - mu * (floor * delta_spend - delta_rev)`; the original
  derivation wasn't recoverable from the note alone, and since `gpc.guardrails`' G8 is the actual
  floor-enforcing backstop regardless of which sizing heuristic chooses candidates, this was not
  treated as blocking. Worth revisiting once `harness_eval`'s lift-vs-cost numbers are in.
- **Sibling cost model.** Matches the handoff's correction: sibling collision does not inflate
  price; it costs a futile follower raise and a possibly-wrong leader. Applied to
  `00-problem-map-and-recommendation.md`'s SG3 row (M6); checked `A-procllm-htn-harness.md` for
  the same issue and found it didn't actually have it.
- **Incrementality's organic-rank prior (E8)** is deferred — the type-level shrinkage already
  pulls thin SKUs toward a directionally similar place; not blocking for M1.

## Correctness fix: the `M_CompetitorCut` incrementality bug

Found by an independent review session (not by any test in this repo) reading
`harness_eval/probes.py`'s own E1 output: `harness/htn/methods.py`'s original `M_CompetitorCut`
cut competitor-keyword MISSES cells straight to their best-dROAS option, skipping the patience
ladder, on the claim that competitor keywords have "~0 incrementality" so a fast cut costs ~0
offtake. **That premise was backwards.** E1's beta_competition ~0 means iota_competition ~1 —
competitor keywords are the portfolio's **most** incremental lever (a competitor-keyword searcher
would not have bought Aurel organically; a brand-keyword searcher, at iota ~0.12-0.20, very likely
would have). The "faster competitor cuts" idea in the original handoff notes was reading
competitor's poor *direct* ROAS (goal_droas ~1.6 vs. brand's 9.0) — a different axis; a low-dROAS
keyword can still be highly incremental, and this one is.

`M_CompetitorCut` has been **removed**, not patched — competitor MISSES cells now take the same
ladder-paced `m_base_cuts` path as brand/generic. `tests/harness/test_scenarios.py`'s S2 test was
rewritten from asserting the old (wrong) fast-cut behaviour to a regression guard that the special
case doesn't come back. The M1 gate was re-run after the fix (table below) and still passes — the
lift now rests on `iota`-weighted raise sizing (`m_reprice_raises`/`tools/sizing.py`, which was
always correct, since it reads the real `iota_lookup` value rather than a hand-written claim), not
on the bug.

**What this says about the test suite up to this point**: every existing test checked that the
(wrong) special case behaved consistently with *its own* wrong premise, which a self-consistent
wrong premise will happily keep passing forever. A green suite confirmed the code did what it was
written to do; it didn't confirm what it was written to do was correct. Worth remembering for
anything not yet independently reviewed.

## LLM-layer cost-tracking bugs (found in the same review pass)

Three more, all in `harness/llm/`, none caught by the 30+ LLM-layer tests that existed before this
pass (each tested the code against its own assumptions, which held internally even though two of
the three assumptions were wrong):

1. **Replay cache key didn't include the model.** Switching `LLM_MODEL` while reusing a cache
   directory could silently replay a different model's cached response. Fixed: `model` is now
   part of `harness/llm/replay.py::cache_key`.
2. **A cache hit never credited the wrapped `Meter`'s running total** — `usage_of()`/the trace
   undercounted cost for anything served from cache. Fixed: `ReplayClient._credit_cached_usage()`
   on every cache-hit path.
3. **The per-run LLM budget (`LLM_MAX_USD_PER_RUN`) was actually enforced per-simulation** — one
   `Meter`, built once, reused across all 6 runs in a `simulate()` call, checked against its
   lifetime total. Fixed: `Meter.run_usage` (resets via `reset_run()`) is now what the budget
   check reads; `harness/policy.py` calls `reset_run_budget(llm)` at the start of every run.

A fourth, found while fixing the above rather than reported: `leaf()` dropped a response's
`usage` to `None` whenever validation failed, even though a response that came back and failed
validation still made a real, billed call. Fixed alongside the others; `leaf()`'s returned `meta`
now also carries the raw pre-validation `raw_response` for the first time, for anyone reading a
trace later.

All four fixes have dedicated regression tests (`tests/harness/test_llm.py`,
`tests/harness/test_leaves.py`) that fail against the pre-fix code by construction — see the build
log for the full list. None of this changes the M1 gate numbers (these bugs are all in the LLM
layer, which M1's `HTNToolsOnly` never touches); they matter for M3's `HTNHarness` at depth L1/L2
and for any future `harness_eval` run with `LLM_MODE` set to something other than `off`, neither
of which has been exercised at scale yet (see "standing open items" below).

## Verification run (M1 gate)

`python -m gpc.score --policy harness.policy:HTNToolsOnly --seed {7,11,23,42}`, dev scenario.
**Current numbers, post the `M_CompetitorCut` removal** (see "Correctness fix: the
`M_CompetitorCut` incrementality bug" below) — the original M1 gate table from before that fix is
kept in the build log's M1 entry for the record, not reproduced here, since this is now the real
behaviour:

| seed | roas_constraint_met | direct_roas | roas_floor | offtake_vs_baseline_pct | shipped/proposed |
|---|---|---|---|---|---|
| 7  | true | 4.793 | 4.535 | +0.36 | 64/64 |
| 11 | true | 4.607 | 4.006 | +0.70 | 103/103 |
| 23 | true | 4.457 | 4.090 | +0.89 | 99/99 |
| 42 | true | 5.165 | 4.721 | +0.95 | 74/74 |

No fallback to `DeterministicTraversal` on any seed. `git diff --stat gpc/market.py
gpc/guardrails.py gpc/runner.py gpc/score.py` is empty throughout (verified — `gpc/` untouched).

## M2 — LLM layer (done)

Built `harness/llm/{client,providers,replay,meter,faults}.py` and
`harness/leaves/{schemas,run}.py`, to spec with no deviations worth flagging. 30 tests
(MockLLM only, no network): provider routing, replay-cache determinism (proven against a mock
that would return something *different* on a real second call), meter cost/budget, every
`FAULT_INJECT` mode, and `leaf()`'s behaviour under each. The user supplied an OpenRouter key and
model (`z-ai/glm-5.3-flashx`) in `grid-path-challenge/.env` (gitignored); one live smoke test
outside pytest confirmed the full stack (`build_llm_stack` -> `ReplayClient` -> `Meter` ->
`FaultInjectingClient` -> `OpenRouterClient` -> real API) round-trips correctly. Caveat:
`meter.price_for()` has no price-table row for `glm-*`, so cost figures involving this model are
an approximation (flat $3/$15-per-M-token fallback), not a measured price — add a real row before
trusting a cost number built on it.

**Not wired into anything yet (at the time M2 closed)**: `HTNHarness` was still identical to
`HTNToolsOnly`. That was M3, done next.

## M3 — leaves wired into methods (done)

`harness/htn/llm_methods.py` adds five leaf-aided methods, each a no-op when `llm is None`:
`sibling_tiebreak` (L3, only on a near-tie), `shock_raises` (L2, via the new `tools/shocks.py`),
`adjust_raise_sizes` (L1, tier-B raises only), `explore_candidates` (L4, capped, disabled by
default), `review_veto` (L6, depth L2 only, veto-only). `harness/leaves/prompts/*.v1.md` +
`render.py` hold the actual prompt text. `HTNHarness` keeps its own
`(campaign_id, keyword_id) -> [day, ...]` action log across runs so `tools/shocks.py` can flag
E5's own-action confounding without guessing at it from the data. Verified `HTNHarness(llm=None)`
byte-identical to `HTNToolsOnly` by diffing `summarize()` output, not just asserting it; ran the
L1 path end-to-end with a `MockLLM` forced to answer "yes" to every judgment and got real
`M_Explore`/shock-raise actions through sizing, precheck and `apply_guardrails` without error.

11 S1-S10 scenario tests (`tests/harness/test_scenarios.py`), S9 split in two (coarse whole-policy
fallback vs. fine per-leaf absorption — the fail-soft doc's three levels). One correctness fix
found via S10's own test: the headroom allowance schedule left the *last* run under-spending its
remaining headroom (nothing carries past run 6) — fixed in `tools/headroom.py`.

## M4 — `harness_eval` (done)

`worlds.py`: search seeds (7/11/23/42), held-out seeds (101/202), and 6 perturbed scenarios
(P1-P6, each moving one documented thing in the dev scenario's own shock list — never inventing a
new truth parameter, never touching the eval scenario). **Still an open item for Gobblecube**:
whether self-authored perturbed scenarios are acceptable for offline validation at all.

`run_matrix.py`: cost-free arms (`no_op`/`baseline`/`tools_only`) always run; LLM arms (`full` +
a leave-one-out ablation per leaf, via a `LeafAblationLLM` wrapper) only run if `LLM_MODE !=
"off"` — this script never flips that switch, so `make harness-eval` never spends money as a side
effect of running it. First real result: `tools_only` beats baseline by **+0.88% on held-out seed
101** — a seed that had zero influence on any design decision in this build, the strongest
evidence yet that the lift isn't an artifact of tuning against the seeds used throughout M1-M3.

`probes.py`: re-derives E1/E2/E3/E9/E10 from `data/` (the baseline's own shipped trajectory),
independently of the earlier hand-written evidence table — and lands within rounding of it:

| Evidence | Report said | Probe recovered |
|---|---|---|
| E1 incrementality | brand -0.88, generic -0.50, competitor ~0 | -0.8794, -0.4978, -0.0096 |
| E2 contested | 100/110 cells, 40/50 markets | 100/110 cells, 40/50 markets (exact) |
| E3 chronic run-out | 6 named campaigns | the same 6 (exact set) |
| E9 ROAS | 4.97x vs 4.54x floor | 4.9667x vs 4.5351x floor |
| E10 blocked share | ~15% | 15.9% |

The E4/E5 shock-recall scan is noisier (no multiple-testing correction across ~100 simultaneous
z-tests per run) — a documented caveat, not tuned away, since it feeds a leaf's judgment rather
than deciding anything on its own.

## M5 — trace + S2 hooks (done)

`harness/trace/{schema,writer}.py`: `RunTrace` (policy, run/day/date, params version, depth, an
`obs_digest` hash, candidate/precheck/action counts, every leaf call's `{leaf, outcome,
wall_clock_s, usage}`, cumulative LLM usage via the new `harness.llm.meter.usage_of` helper,
fallback reason). Off by default (`TRACE_DIR` unset); `maybe_write_trace` appends one JSONL line
per run when it's set, including on the exception-fallback path (so a fallback shows up in the
trace, not just in a log message). **Bug caught and fixed**: the first version's `_n()` helper
used `run_trace.get(key, []) or []` to default a missing candidates frame — `or` forces a
truthiness check, and a non-empty pandas DataFrame raises `ValueError: truth value ... is
ambiguous` rather than returning truthy/falsy, so every real (non-empty) run crashed into the
exception-fallback path silently. Caught by actually running `HTNToolsOnly` with `TRACE_DIR` set
end-to-end (not just unit-testing `build_trace` in isolation) and noticing the fallback fired.

`harness/s2/{arms,reward,learner_stub}.py`: `ArmRegistry` (11 default arms — headroom
front/back-load, shock-z 2.0/2.5/3.0, explore on/off, depth L0/L1/L2), `pair_reward`/
`aggregate_reward` (a `score = None` floor gate — an arm can't look good by averaging over worlds
where it broke the floor), `propose_params` (best qualifying arm, with a CLI). `Params.to_dict()`
added to `harness/config.py` as the inverse of `_from_dict`, so a proposed arm round-trips through
a `PARAMS_PATH` file; verified round-trip equality directly, not just that it doesn't error.
**Not built**: a per-keyword-type depth override arm (the plan's one-liner mentions it;
`Params.depth` is a single global field, and adding that dimension is real plumbing through every
depth check, not a registry entry) and the actual S2-arms-x-worlds sweep a cron job would run to
produce `learner_stub`'s input — `harness_eval/run_matrix.py` sweeps policy arms, not params arms;
wiring those together is the natural next step, flagged rather than silently assumed done.

19 new tests (`tests/harness/{test_trace,test_s2}.py`), all passing. Full suite after M5: 99 fast
+ 8 slow = 107, all green.

## M6 — docs (done)

This doc, `A2-tests-and-scenarios.md` (test catalogue, S1-S10 with every plan-vs-actual
reinterpretation named), `A3-data-evidence.md` (E1-E10 independently re-derived from `data/` via
`harness_eval/probes.py`, landing within rounding of the original hand-written numbers on every
item checked), `systems-1-2-3-roadmap.md` (System 1 built, System 2 hooks-only with the concrete
gap named, System 3 a design note). Applied the sibling-cost wording fix to
`00-problem-map-and-recommendation.md`'s SG3 row (sibling collision displaces a slot, it doesn't
inflate price) — checked `A-procllm-htn-harness.md` for the same issue and found it didn't
actually have it, so left unchanged rather than fixing something that wasn't broken.

## Standing open items (not milestones — things a future session should pick up)

- **Gobblecube confirmations still pending** (plan's own open items, never answered this build):
  read-only `apply_guardrails` dry-run allowed? committed replay cache acceptable for
  reproducibility? self-authored perturbed scenarios (P1-P6) acceptable for offline validation?
- **S2-arms x worlds sweep** — the thing that would actually produce `learner_stub`'s input from
  real data, not a hand-fed JSON file.
- **`meter.price_for()` has no row for `glm-*`** (the configured model) — cost figures involving
  it are a flat-rate approximation, not measured. (Spun off as background task `task_861787f2`.)
- **E4/E5 shock-recall** has no multiple-testing correction — fine for feeding a leaf's judgment,
  not yet validated as a named-shock recall check against the three specific `dev.json` shocks.
- **A real LLM-arm `harness_eval` run** (`LLM_MODE=record`, real spend) has not been executed —
  everything LLM-related has been tested with `MockLLM` plus one minimal live smoke call; the
  plan's ~$40 evaluation budget hasn't been touched. This is also the first real exercise the
  cost-tracking fixes above (cache-hit crediting, per-run budget reset) haven't had yet — they're
  tested with mocks, not proven against a real multi-run `record`/`replay` cycle.
- **`leaf()`'s trace record still doesn't include the rendered prompt text** (`system`/`user`),
  only the outcome, usage and raw response — flagged by the same review that found the four bugs
  above as "results thrown away instead of traced", now partially true rather than fully true.
  Spun off as background task `task_3eaa54e8`.
