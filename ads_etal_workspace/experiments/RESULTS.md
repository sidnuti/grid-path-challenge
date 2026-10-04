# Results: slice-and-dice measurement of the System 1 harness

Snapshot 2026-10-03. Code under test: `grid-path-challenge` commit `483ea9e`, hash `63196db22b74`. All simulations $0 (no real LLM call).
Design and limits: `EXPERIMENT_DESIGN.md`. Narrative and corrections: `../logs/2026-10-03-experiments-log.md`. Findings with caveats:
`../runtime_findings/FINDINGS.md`. Raw tables: `results/`. Claim-by-claim check against `../presentations/`: `../runtime_findings/PRESENTATION_TALLY.md`.
Statistics: Student-t 95% CI, exact sign-flip p (n<=16), paired on world+seed. A lift counts only if the ROAS floor is met.

| Experiment | Status | Result | File |
|---|---|---|---|
| X0 measurement checks | done | books exact; oracle error 0 on clean auctions; A/A = 0; noise floor MDE 0.13-0.21pp at 6 worlds; floor margin per arm | `results/x0_measurement.md` |
| Headline lift | done | L0 vs baseline +0.23% (0.07..0.40, dev6); vs no-op +0.13% (0.03..0.23, fresh20) | x0, `x2_ablation_fresh20.md` |
| X1 modules vs truth | done | grid spend forecast 1.7x high; iota ~0 within-type correlation; sibling leader right 70% / 56% near-tie; 46-105k INR unused slack; shocks: OSA yes, price 43%/8%, demand 12% | `results/x1_modules.md` |
| X2 ablation (dev6, fresh20) | done | gate costs +0.86pp (20/20); cuts are floor insurance (no-cuts +0.05, floor 18/20); no gate+no cuts +1.06 but floor 11/20 | `x2_ablation_dev6.md`, `_fresh20.md` |
| Gate sweep | done | the lever is the minimum allowance: 1000/2000/3000/5000 -> +0.41/+0.70/+0.80/+0.86pp | `x2_ablation_gate_sweep.md` |
| 1b state-dependent minimum | done, **confirmed** | `sm_r1500_c1.0`: fresh20 +0.53; unseen 2001-2010 +0.32 (0.23..0.41), floor 10/10, margin 0.287 vs L0 0.304 | `x2_ablation_state_min.md`, `_confirm2001.md`, `_reserved10.md` |
| X3.3 actions | done | cuts 0.75 offtake/INR at marginal dROAS 1.25 (raise portfolio ROAS); budget raises 1.76; CPM raises 3.14; spend projections 1.5-4x low | `x3_3_action_effects.md`, `x3_3_floor_view.md` |
| X5.1 / X5.2 scripted LLM | done | no leaf improves offtake, oracle included; acting leaves (L6, L4) lower it; L1/L2/L6 fire ~0.3/1/0.2 per run | `x5_llm_aided.md` |
| X7.3 perturbed worlds | done (234 sims) | gate relaxation +0.4..1.1pp in all 13 worlds; `sm_r1500_c1.0` +0.51 (value) / +0.57 (shock), floor met 39/39; fixed 3000 and no-gate 1 floor miss each; no cuts: floor 12/18 in shock worlds | `x7_generalisation.md` |
| X3.1 bid dose-response | done (2 seeds) | grid assumes slot 1 is won at the median price: raise predictions are flat while true live-bid slot-1 share is 0.42-0.83; explains both the 1.7x level over-forecast and the 1.5-4x marginal under-forecast; competition raises lower offtake | `x3_1_bid_dose_seed{7,11}_run3.md` |
| W0 old-harness lift | done | old commit `0b73557` re-run from a worktree: **+0.824% reproduced exactly**; the `483ea9e` fixes cost **-0.59pp** (0.40..0.78, 6/6) | `w0_old_vs_new_harness.md` |
| X4, X6, X3.2, paid LLM slice | not started | | |

## The five results that matter
1. **The harness's value comes from raises; the headroom gate throttles it; cuts pay for it.** Removing the gate: +0.86pp (20/20 worlds). Cuts remove spend at ROAS 1.25
   (floor ~4.34), so they raise portfolio ROAS and make raises affordable.
2. **The gate's cost is its minimum allowance.** A state-dependent minimum recovers +0.3 to +0.5pp while keeping L0's floor margin; confirmed once on untouched seeds with a rule
   written in advance. A fixed 3000 gains more but had a floor miss (void score) in 1 of 20 unseen worlds.
3. **The modules' own estimates are weak:** forecast 1.7x high, iota uncorrelated within type, siblings 56-70%, shock detector OSA-only.
4. **No LLM leaf adds offtake in simulation, even answering from hidden truth.** Leaves barely trigger, and the ones that act lower offtake.
5. **The old +0.82% was right for the old code and is reproduced exactly from it (W0); today's code gives +0.23%.** The `483ea9e` correctness fixes cost 0.59pp because
   sizing now respects an allowance that is too tight. The state-dependent minimum (result 2) recovers most of it while keeping sizing correct.

## Corrections made along the way
Percentile bootstrap -> Student-t; "cuts net-negative" retracted (fresh20); "gate buys margin" -> cuts do; MDE attribution fixed; seeds 101/202 no longer held out; fixed 3000 not safe;
scripted-LLM regex bug and X5 trigger-table double count caught by tests/cross-check. Full list: log, section "Review corrections" onward.

## Limitations
Dev-structure worlds only until X7.3; 6 worlds for X0/X1/X3.3/X5; 2001-2010 had no thin-margin world; X3.3 is within-week; oracle leaf answers are proxies; no real LLM; `harness/` is not edited here, so every fix is a recommendation.
