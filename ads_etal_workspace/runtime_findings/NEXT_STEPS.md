# Next implementations (revised 2026-10-03, after 1b, X1, X5.1)

Done since the last revision: gate sweep (item 1), state-dependent minimum (1b, **confirmed on untouched seeds 2001-2010**), X1 module scoring, floor-margin
reporting, X5.1/X5.2 scripted-LLM bounds, EXPERIMENT_DESIGN.md. Also done: X7.3 (13 perturbed worlds: gate and cuts findings generalise), X3.1 (bid dose-response), W0 (another session), exploratory no_generic_cuts (not supported).

| # | Item | Highlights / gets us | Cost | Limitations |
|---|---|---|---|---|
| 1 | **Hand the gate fix to the harness owner**: `sm_r1500_c1.0` (run 1: 1500 INR/day; later runs: min(3000, 1.0 x banked headroom)) | +0.3 to +0.5pp at L0's floor margin; one-paragraph spec plus the evidence | Writing only (`harness/` is not ours to edit) | Confirmed on dev-structure worlds only; X7.3 is the generalisation test |
| 2 | **X7.3 perturbed worlds** (running/queued) for L0, no-gate, fixed 3000, no-cuts; **add `sm_r1500_c1.0`** | Does the gate result and the cuts-as-insurance picture hold when values and shocks differ (the eval scenario's situation) | ~195 sims (+ ~39 for the sm arm) | Self-authored perturbations |
| 3 | **X3.1 bid dose-response** (queued) | Tests the 1.7x forecast gap and the marginal response shape; decides if the grid needs fixing | ~1 h | Single-week effects |
| 4 | **Fix proposals for modules** after X3.1: grid level forecast; iota estimator (oracle-iota arm to test whether accuracy changes decisions) | The two weakest modules (forecast 1.7x, iota ~0 correlation) | Medium | Needs the oracle-iota value-of-information test first |
| 5 | **LLM layer: trigger design** (L1/L2/L6 fire 0.3 / 1 / 0.2 times per run) and a better-than-proxy oracle | X5.1 says no leaf adds offtake as configured; the work is what the leaves decide, not paying for calls | Medium | Oracle quality bounds what X5 can prove |
| 6 | **Real LLM slice ($3 cap)**: hold until 5 changes the triggers | Real-model validity/variance | Paid | Not worth it on current X5.1 evidence |
| 7 | **X6 traced narrative run**, X4 leaf plumbing, X3.2 budget dose-response, `RESULTS.md` refresh | Readable story, completeness | Low | One seed |

## Status update (2026-10-03, after 1b)
- Done: item 1 (gate sweep) and 1b (state-dependent minimum; confirmed on untouched seeds 2001-2010, floor 10/10, +0.32pp).
- Open on the gate: test the recommendation in perturbed/eval-like worlds (X7.3, queued by the other session) before treating +0.3-0.5pp as general.
- Seeds 303-322, 1001-1010, 2001-2010 are now all used; the next confirmation needs a fresh set (e.g. 3001-3010).

_All recommendations and suggestions are consolidated in `recommendations/` (start at `recommendations/README.md`)._
