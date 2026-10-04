# Experiment design: slice-and-dice measurement of the System 1 harness

Plan of record: `plan_copies/2026-10-03-slice-and-dice-experiments-plan.md`. Narrative log: `logs/2026-10-03-experiments-log.md`.
Findings: `runtime_findings/FINDINGS.md`; next steps: `runtime_findings/NEXT_STEPS.md`. This file says **what each experiment asks,
how it is measured, what would count as an answer, and what it cannot tell us.**

## 0. Ground rules

- No edits to `gpc/`, `harness/`, `harness_eval/` (another session owns them). All code is in `experiments/`.
- Experiments are offline tooling and may read `World.truth`. The harness itself never does.
- Every comparison is **paired**: same seed and scenario, so the same market draws. A/A difference is exactly 0 (tested), so any
  non-zero paired difference is a policy effect.
- Statistics: Student-t 95% CI (not the percentile bootstrap, which is too narrow at n=6), exact sign-flip p at n<=16, and each
  comparison's own minimum detectable effect.
- **A lift only counts if the ROAS floor is met.** A run that misses the floor has a void score, so every table carries floor status and
  margin (direct ROAS - floor).
- Seed hygiene: dev6 = 7/11/23/42/101/202 (used for building and early findings; 101/202 are no longer held out); fresh20 = 303-322
  (tuning); 1001-1010 used once for a confirmation (now spent); 2001-2010 reserved for the next confirmation.
- Cost: everything so far is $0 (scripted LLMs). Paid LLM slice is capped at $3 and gated on X5.1.
- Cache: every simulation result is keyed by arm, seed, scenario and a hash of all `gpc/` and `harness/` sources, so a harness edit
  invalidates results rather than mixing them silently.

## 1. The funnel and what a policy can see

| Stage | Metric | Visible to a policy? |
|---|---|---|
| Demand | searches per market x daypart | No (oracle reconstructs it) |
| Auction | impression share by slot (1/5/9/13) | slot mix yes, share no |
| Delivery | impressions, CPM, spend, run-out | Yes |
| Conversion | orders per 1000 impressions | Yes |
| Direct value | ad revenue, **direct ROAS** (the floor metric) | Yes |
| Incremental value | true incremental units, true iROAS, cannibalised units | No |
| Outcome | organic + ad units, **offtake INR** (the score) | Yes |

Clicks are not modelled by the simulator; impression share and orders per impression stand in for click-through and conversion.

## 2. Experiments

### Measurement layer (`lib/`) and X0 (are the measurements right?)
Oracle (searches, potential impressions, true incremental units), funnel, switchable L0 policy, per-action counterfactual replay,
hash-stamped cache, paired statistics. X0 checks: accounting identities (X0.1), oracle reconstructs served impressions on clean auctions
(X0.2), noise floor and MDE (X0.3), lift decomposition into ad vs organic and direct vs true iROAS (X0.4), lift by week (X0.5), floor margin
(X0.6). **Answer if:** identities exact, oracle error 0 on clean auctions. **Cannot tell:** whether findings generalise beyond dev.

### X1: each module scored against truth (`x1_modules/`)
Live-bid forecast vs the realised week (X1.1); incrementality estimate vs `incrementality x organic_damp` (X1.2); chosen sibling leader vs
highest true value per impression (X1.3); headroom/allowance vs end-of-window slack (X1.4); what precheck lets through (X1.5); shock
detector precision/recall/lead vs injected shocks, via a recorder that runs `detect_shocks` beside L0 without changing its actions (X1.6).
**Cannot tell:** why a module is off (mechanism is hypothesised, then tested by X3).

### X2: which components earn their keep (`x2_ablation/`)
Switchable L0 (reprice, budget raises, cuts, sibling holds, headroom gate, precheck) and parameter arms (allowance scale, minimum
allowance, state-dependent minimum). Paired vs full L0 and vs no-op, with floor status. **Cannot tell:** interactions beyond the factorial
arms run; effects on worlds with different values (X7).

### X3: harness vs market (`x3_market/`)
X3.1 bid dose-response: for 12 cells, re-simulate a week at -50..+50% bid, compare slot mix, impressions, orders, spend, revenue, offtake
with the grid's prediction. X3.3: true effect of each shipped action by removing it (exact paired replay) and its marginal ROAS vs the floor.
**Cannot tell:** carry-over beyond the action's own week (full-run X2 comparisons include it).

### X5: can an LLM leaf matter? (`x5_llm_aided/`, `lib/scripted_llm.py`)
Scripted leaves (always-yes, always-no, random, oracle-from-truth), one leaf at a time and all together, at default and recalibrated
params; call counts and trigger rates (X5.2). The oracle is an **upper bound**, not a realistic model. A leaf whose oracle adds nothing is not
worth paying for. **Cannot tell:** how a real model behaves (that is the paid slice).

### X7: generalisation (`x7_generalisation/`)
Seven one-change value variants of dev (incrementality +-30%, auction sigma 0.2/0.45, appeal rotated, intent x1.25/x0.8) plus
`harness_eval`'s six shock-schedule worlds, 3 fresh seeds each. The private eval scenario "uses different values and shocks", so this is the
closest offline stand-in. **Cannot tell:** behaviour on the real eval scenario.

### Not yet built
X4 (leaf plumbing with real prompts), the capped paid LLM slice, X6 (traced narrative run), X3.2 (budget dose-response), `RESULTS.md`.

## 3. How to run

From `grid-path-challenge/`, with `PYTHONPATH=.:..` and `.venv/bin/python`:

```
python -m pytest ../experiments/tests -q                      # 24+ tests
python -m experiments.run_arms --arms l0 no_op baseline ...   # simulations into the cache (resumable)
python -m experiments.x0_measurement.x0_run                   # then x1_modules.x1_run, x2_ablation.x2_run, x5_llm_aided.x5_run, ...
bash ../experiments/run_x51.sh | run_x73.sh | run_x31.sh      # batch scripts
```
