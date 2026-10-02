# A2 — Tests and scenarios

Companion to `A1-implementation.md`. Catalogues what's actually tested, where, and what passing
means — not the plan's test spec restated, but the real suite as built, with the handful of
places it ended up testing something slightly different from the plan's one-line description
(each one logged here *and* at the point in the test file where the reinterpretation happens, so
a future reader hits the explanation at the point of confusion, not just in this summary).

## How to run it

```
make test              # base sandbox tests (unchanged, pre-existing)
make harness-test       # fast harness tests: tests/harness -m "not slow" (~1-2 min)
make harness-test-slow  # + the 4-seed floor/lift gate (~5 min, full 6-run sims)
```

`pytest.ini` registers the `slow` marker. As of the post-M6 bug-fix pass: **116 fast tests + 8
slow tests = 124 total**,
all passing, zero warnings, across `tests/harness/`, `tests/test_harness_eval.py` and the
pre-existing `tests/test_sandbox.py`.

## Test catalogue

| File | What it covers |
|---|---|
| `tests/test_sandbox.py` | Pre-existing (not ours). Base engine invariants — unaffected by anything in `harness/`, re-run after every milestone to confirm `gpc/` stays untouched. |
| `tests/harness/test_rules.py` | AST scan of every `.py` file under `harness/`: no `gpc.market`/`gpc.scenarios` import, no `harness_eval` import, no `.truth` attribute access, no `open(...)` of a path under `gpc/scenarios`. Plus: a dev `Observation` built the normal way has no `truth` field on its dataclass at all (structural, not just a scan). |
| `tests/harness/test_tools.py` | Incrementality (synthetic recovery + dev-data ordering), siblings (40/50 contested markets, exact), headroom (non-negativity), precheck-vs-`apply_guardrails` (property test, 30 randomized actions per run). |
| `tests/harness/test_tools_only_policy.py` | **Slow.** The M1 gate: floor met + no fallback + blocked share ≥ 90% shipped, parametrized over seeds 7/11/23/42. |
| `tests/harness/test_llm.py` | Provider routing (`openrouter`/`openai`/`anthropic`/`none`/unknown), replay-cache determinism (against a mock that would return something *different* on an uncached second call — proves the cache is doing the work, not luck), meter cost/budget enforcement, every `FAULT_INJECT` mode. MockLLM only, no network. |
| `tests/harness/test_leaves.py` | Schema validate/clip (malformed -> default, out-of-range -> clipped, unknown id -> default), `leaf()`'s behaviour under each `FAULT_INJECT` mode. |
| `tests/harness/test_scenarios.py` | S1-S10 (see below). |
| `tests/harness/test_trace.py` | `TRACE_DIR` unset/empty = no-op; `build_trace` field counts match the run-trace dict it's built from; `obs_digest` deterministic and change-sensitive; JSONL round-trip (write, read back, append across calls). |
| `tests/harness/test_s2.py` | `ArmRegistry` materialization; `aggregate_reward`'s floor-gate (`score = None` if any world in the group misses the floor); `propose_params`'s best-qualifying-arm selection and its fallback when nothing qualifies. |
| `tests/test_harness_eval.py` | World coverage (search/held-out/perturbed counts), cost-free-only arm selection when `LLM_MODE=off`, `LeafAblationLLM`, one real `run_matrix` call on one world. Flat file, not a `tests/harness_eval/` package — see its own docstring for why (the M0 name-collision lesson). |

## S1-S10 (`tests/harness/test_scenarios.py`)

All on the dev warm-up `Observation` (seed 7, 28 days) or a targeted perturbation of it — never a
dev-scenario magnitude as the assertion itself, per the plan's own caveat about confounded reach
series.

| ID | Plan's one-liner | What's actually asserted | Note |
|---|---|---|---|
| S1 | No raise on a slot-1 brand cell | `precheck` blocks (`G3`) an `increase_cpm` on a cell with `slot1_share_7d >= 0.80` | — |
| S2 | A competitor miss is cut >= 20% at once and redeployed | `m_base_cuts` treats a competitor MISSES cell exactly like any other — no special-case lookup by keyword type at all | **Reinterpreted, twice.** First (M3) for the missing redeploy/transport step (`tools/sizing.py` dropped the plan's `linprog` step). Then (post-M4, after an independent review) the scenario's entire premise was found backwards: E1 says competitor keywords have the *highest* incrementality in the portfolio (iota ~1, not ~0 — beta ~0 cancels in the `iota = 1 + beta` conversion the wrong direction from what an earlier pass assumed), so a fast, ladder-skipping cut is the *expensive* move, not the cheap one. The `M_CompetitorCut` method this test originally checked was removed; this now tests that it doesn't come back, not that it works. See `harness/htn/methods.py`'s module docstring and `logs/2026-10-02-build-log.md` for the full correction. |
| S3 | Followers step down, the leader holds | A held follower's `(campaign_id, keyword_id)` never appears in `m_reprice_raises`' output | — |
| S4 | A budget raise is valid under G5/G7 after trimming a weak keyword | `m_budget_raises` only proposes a raise when the campaign's spend-weighted shrunk dROAS already clears 90% of its spend-weighted goal (the G7 gate itself), and that raise passes `precheck` | **Reinterpreted.** "After trimming a weak keyword" implies a transport step moving money between a cut and this raise, which doesn't exist here (same reason as S2) — tested as a direct gate check instead. |
| S5 | A surge gives raises on clearing cells | `shock_raises` with a `MockLLM` confirming `is_shock=True, direction="surge"` produces a raise above the live bid, on a cell whose verdict *isn't* CLEARS | Deliberately on a non-CLEARS cell — that's the point of M_Shock (SG5): reacting before the mechanical verdict catches up. |
| S6 | No increases during low OSA, dip days masked | A perturbed `Observation` (OSA forced to 0.30 for one SKU x city x 3 days) makes `precheck` block (`G4`) an `increase_cpm` there | "Dip days masked" (excluding them from the *next* verdict's miss-streak count) is G4's job already, inherited from `gpc.guardrails`/`gpc.engine.loop` unchanged — not separately re-implemented or re-tested here. |
| S7 | Capped exploration | `explore_candidates` with `explore_max_thin_cells=1` and a mock that asks for more spend than the cap allows returns at most 1 candidate, and its predicted spend fits `explore_spend_cap_inr_day` | — |
| S8 | Retreat on a price shock | `shock_raises` with `direction="drop"` produces **zero** raises | **Reinterpreted.** "Retreat" -> "don't chase a price shock with a raise." No mechanical signal in this build says a *price*-direction shock (as opposed to a demand drop) should trigger an *active* cut beyond what the normal MISSES ladder already does — logged as a genuine scope gap, not quietly papered over. |
| S9 | Baseline fallback on LLM failure | Split into two, matching the fail-soft doc's actual two finer levels: (a) an exception deep inside `_harness_recommend` (not just an LLM call) makes `HTNHarness.recommend` fall back to `DeterministicTraversal` byte-for-byte; (b) an LLM that raises on *every* call does **not** trigger that fallback — each leaf absorbs its own failure into a default, and the run proceeds identically to `HTNToolsOnly` | Confirms both fail-soft levels exist and don't collapse into each other. |
| S10 | Run 6 uses the full allowance minus the margin | On a real 6th-run `Observation` (63-day simulation, not fabricated), `compute_headroom`'s `allowance_inr_day == headroom_inr_day` exactly at run 6, and `< headroom_inr_day` at run 5 (when there's headroom to withhold) | This was a genuine bug the test caught: the allowance schedule originally left run 6 under-spent too, since nothing special-cased "last run, nothing carries forward." Fixed in `tools/headroom.py`. |

## Fail-soft, end to end

Three levels, each with its own test coverage:

1. **A leaf failure returns that leaf's default.** `test_leaves.py`'s `FAULT_INJECT`-parametrized
   tests, plus S9b.
2. **A verify/guardrail failure falls back to baseline actions for that lever.** Implicit in
   every scenario test that exercises `precheck`/`filter_precheck` — nothing in this build adds a
   *separate* "verify" repair step beyond `gpc.guardrails`' own clamping (G1/G2/G6) and portfolio
   trim (G8), which are the plan's "≤ 1 repair" already, unmodified.
3. **Any other exception falls back to `DeterministicTraversal`.** S9a, plus the two real bugs
   caught this way during M1/M4 development (an un-indexed `pacing` frame, a non-vectorized
   `max()`) — both fixed, not papered over by the fallback catching them silently; the fallback
   is a safety net for what wasn't anticipated, not a substitute for fixing what was found.

## What M3's test pass actually caught

Worth stating plainly rather than letting the pass/fail count speak for itself: of the 11 S1-S10
tests, 10 passed on the first write; S2 failed because the initial assertion (a fixed "≥ 20%
cut") happened to not match whichever bid step was best-dROAS on the specific fixture cell that
run, which would have made the test fixture-lucky rather than actually pinning down the
mechanism it claimed to test. Rewritten to assert the real structural difference between
`M_CompetitorCut` and `M_Base` instead (both since superseded — see below). The build log
(`logs/2026-10-02-build-log.md`) has the full narrative; this doc keeps the standing catalogue.

## What a test suite doesn't catch: the post-M6 independent review

An important caveat on everything above. After M6, an independent review session (reading the
same code plus its own fresh `run_matrix`/probe output) found four real bugs — one of them a
genuine economic-reasoning error in `M_CompetitorCut` (it cut the portfolio's *most* incremental
keyword type fastest, believing the opposite), the other three cost-accounting bugs in
`harness/llm/{replay,meter}.py` — that none of the 99+ tests passing at the time had caught.
Every one was a case of the code being internally consistent with a wrong premise: the S2 test
above checked that `M_CompetitorCut` behaved the way `M_CompetitorCut` intended to behave, which
it did, correctly, on a false premise. A test built from the same understanding as the code it
tests will validate that understanding, not check it against reality. All four are fixed now
(`harness/htn/methods.py`, `harness/llm/{replay,meter}.py`'s docstrings have the specifics), each
with a regression test that fails against the pre-fix code by construction — but the fact that it
took a second, independent pass to find them, not the first pass's test suite, is the more durable
lesson than any individual fix.
