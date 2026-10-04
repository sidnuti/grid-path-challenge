# Experiments log — slice-and-dice measurement of the System 1 harness

Plan: `plan_copies/2026-10-03-slice-and-dice-experiments-plan.md`. Code: `experiments/`. Results: `experiments/results/`
(raw) and `experiments/RESULTS.md` (findings). This log is the running narrative: what was built, what broke,
what was decided.

## Session 2026-10-03

### Setup and the moving target

The harness is being edited by another session while these experiments are built. Between my first
`l0` run and my second the code hash changed three times. Rewrites that landed mid-session: sizing
(greedy ratio knapsack that respects the allowance), a minimum-allowance parameter in `headroom.py`, and
a precheck pass on raises **before** sizing in `_tools_only_recommend`. Consequences handled:

- `experiments/lib/runs.py` stamps every cached simulation with a hash of all `gpc/` and `harness/`
  sources, and `load_latest` reports which hash each result came from. Result files record the hashes
  they saw (`_code_hashes_seen`); a mixed set is marked `(MIXED)`.
- The switchable L0 policy mirrors the pipeline order of `_tools_only_recommend`. A test asserts it is
  identical to `HTNToolsOnly`. It **caught the drift** the first time (my policy lacked the new pre-sizing
  precheck); fixed by mirroring the new order.

### Measurement layer (`experiments/lib/`)

`oracle.py` (searches + potential impressions + true incremental units, from `World.truth`), `funnel.py`
(metric tree), `switchable_policy.py` (ablation switches), `counterfactual.py` (replay), `direct_sim.py`
(guardrail-free loop + exact single-week replay), `runs.py` (hash-stamped cache), `stats.py`, `report.py`.

Tests (`experiments/tests/test_lib.py`): switchable == `HTNToolsOnly`; A/A difference exactly 0; oracle
reconstructs emitted impressions; incremental-units identities; funnel identities; outcome == `gpc.score`;
replay policy reproduces a run; **single-week replay is exact**; scheduled no-op == no-op arm; stats helpers.

**Finding while building the oracle test (an X0.2 result):** the first version of the check failed with errors up to
128 impressions. Every error was in the *evening* daypart, in contested markets, on campaigns that had **not**
run out. Cause: the market drops a campaign from later dayparts' auctions once its budget is gone, which changes
its siblings' shares. The oracle was right; the check only excluded the ran-out campaign's own rows. The
fix is `clean_mask`, which excludes every market containing a ran-out campaign. Lesson recorded for the
measurement layer: budget truncation is not local to the truncated campaign.

Test mistakes fixed along the way: `worlds_needed(0.27, 0.1)` is 58 (ceil of 57.2), not 57.

### Status when the session stopped (usage limit)

**Done and tested:** measurement layer (`experiments/lib/`), 12 tests, all passing at last run
(the 3 newest tests, added after that run, have not been executed yet).
**Written but never run:** `x0_measurement/x0_run.py` (needs the batch below to finish) and
`x3_market/x3_3_action_effects.py`. `lib/oracle.py::cell_truth` was added after the last test run.
**Background job still running:** `python -m experiments.run_arms --jobs 4` (72 simulations: 12 arms x 6 seeds;
about 28 done; log in `experiments/results/run_arms.log`; results cached in `experiments/results/cache/`).
If the process died, rerun the same command; cached runs are skipped.

**Not started:** X1 module scoring (recorder policy + scripts), X3.1/3.2/3.4/3.5, X2 analysis, X4, X5 (scripted LLMs),
X6 narrative, X7 (parameter-perturbed worlds), the capped paid LLM slice, `EXPERIMENT_DESIGN.md`, `RESULTS.md`,
`run_free.sh`/`run_paid.sh`.

**Next steps, in order:** (1) wait for the batch; (2) run `pytest experiments/tests`, then
`python -m experiments.x0_measurement.x0_run`; (3) run X3.3; (4) write X1 recorder; (5) X2 table from cached arms.
Run everything from `grid-path-challenge/` with `PYTHONPATH=.:..`.

## Session 2026-10-03 (resumed)

- Batch finished: 72/72 runs cached (one stray `l0` seed-7 file from an older code hash; `load_latest` takes the newest).
- Python lives in `grid-path-challenge/.venv/bin/python` (system `python3` has no pytest). Run from
  `grid-path-challenge/` with `PYTHONPATH=.:..`.
- **Tests: 12/12 pass** (67s), including the 3 that had never been run.
- **X0 run** (`results/x0_measurement.md`): books balance exactly (offtake err 0, unit err 0); oracle reconstructs
  emitted impressions exactly on clean auctions (max err 0 in all 12 seed/day samples; 22-72% of rows are clean;
  6-15% of potential impressions are lost to budget exhaustion); A/A = 0 exactly.
  Lift: L0 vs baseline +0.23% (CI 0.13..0.35), vs no-op +0.07% (CI -0.01..0.15, **not distinguishable from zero**).
  Noise floor: MDE at n=6 is ~0.13-0.21pp, so lifts this small need >=20 worlds to resolve at 0.1pp.
  Lift is back-loaded: week 6 carries most of it (+0.85% vs baseline).
  L0's gain over no-op is ad_value +60.9k offset by organic -49.1k; brand ads are ~89% cannibalised (incrementality 0.11).
- **X2 ablation** (`x2_ablation/x2_run.py`, `results/x2_ablation.md`), paired over 6 seeds, vs full L0:
  - `no_headroom_gate` **+0.85pp** (CI 0.67..1.00, all 6 seeds positive): the headroom gate is the dominant drag.
  - `no_cuts` **+0.13pp** (CI 0.04..0.21): cuts cost money net.
  - `cuts_only` -0.37pp vs L0, below no-op: cuts alone are harmful.
  - `no_budget` -0.20pp, `no_precheck` -0.04pp, `no_reprice` -0.04 (CI spans 0), `no_sibling_holds` ~0: budget
    moves earn their keep; reprice/precheck/holds are within noise.
  - Caveat: n=6 worlds; only gate and cuts effects clear the MDE. Mixed code hash is recorded in the JSON.
- X3.3 (`x3_market/x3_3_action_effects.py`) first run launched; >2 min per run, executed in background.

**Still not started:** X1 module scoring, X3.1/3.2/3.4/3.5, X4, X5, X6, X7, paid LLM slice, EXPERIMENT_DESIGN.md,
RESULTS.md, run scripts.

### X3.3 result (321 shipped L0 actions, seeds 7/11/23/42, within-week paired removal; `results/x3_3_action_effects.md`)
- Projections understate spend change: true/pred Δspend = 3.95x for budget raises, 1.47x for CPM raises, 2.18x for CPM cuts.
- Revenue projection: budget raises under-projected 2.96x (true ad rev 164k vs 56k projected); reprice raises ~calibrated in total
  (0.93x) but uncorrelated per action (corr 0.02); cuts ~calibrated in total (1.03x), corr 0.24.
- True offtake per rupee: budget raises 1.76, CPM raises 3.14, **CPM cuts 0.75** (cutting 96k of spend lost 72k offtake):
  consistent with X2 (cuts cost net). Budget raises and reprice raises are where the value is.
- Sizing rank: Spearman 0.41 between projected marginal ratio and true marginal offtake/rupee (n=70) — informative but noisy.
- Cut actions are 78% of all actions (250/321), yet the least efficient. Carry-over past the week is not counted.
- Minor: pandas FutureWarning from groupby.apply in the script (harmless; fix with include_groups=False).

### Review corrections and fresh-seed replication (same day)
Independent review recomputed every headline number from the 72 cached runs (all reproduce) and found overstated readings:
- `stats.py` used a percentile bootstrap (too narrow at n=6). **Fixed:** `summarize` now returns Student-t CI, exact sign-flip p,
  per-sample MDE (bootstrap kept as `boot_lo/hi`). New test `test_t_ci_wider_than_bootstrap_and_signflip_exact` (my first expected
  value was a hand-arithmetic error; code was right). **13/13 tests pass.**
- Corrected claims: baseline-vs-no-op is -0.17 (t CI -0.36..+0.03), not shown to be worse; "only gate and cuts clear MDE" was wrong;
  the gate does not buy margin, cuts do; 101/202 are no longer held out.
- `x2_run.py` now reports t CI, p, own MDE, floor met, min ROAS margin over floor and spend vs L0, for any seed set (`--seeds --tag`).
- Added `no_gate_no_cuts` arm (factorial). Ran 6 arms x 20 fresh seeds (303-322) + the factorial on dev6 (126 runs, same code hash
  `63196db22b74`). Seeds 1001-1010 reserved untouched.
- **Results:** gate removal replicates (+0.86pp, 20/20 worlds better, floor met 20/20). Cuts removal does NOT (+0.05, CI -0.03..0.13,
  8 worse/12 better) and drops floor compliance to 18/20. Removing both: +1.06pp but floor met only 11/20 (score would be void).
  No-op itself misses the floor in 3/20 worlds. The dev6 "cuts are net-negative" conclusion is retracted.
- FINDINGS.md and NEXT_STEPS.md rewritten accordingly. Next: gate sweep with cuts kept, perturbed/eval worlds.

### Item 1: gate sweep with cuts kept (fresh20 = seeds 303-322; confirm on reserved 1001-1010)
Built `PARAM_ARMS` / `make_params` in `lib/switchable_policy.py` (gate arms use the harness's own `Params`; no harness edits) and a
test that the identity override equals `load_params()` and the overrides change only what they say. **14/14 tests pass.**
Sweep (176 sims, hash `63196db22b74`), all with cuts kept, vs full L0, fresh20:
- Scaling the allowance fractions (x1.5 / x2 / x3): +0.04 / +0.10 / +0.16pp. Margin 0 on the headroom: +0.04. Small.
- **The lever is the minimum allowance**: 1000 -> +0.41, 2000 -> +0.70 (min margin 0.148), 3000 -> +0.80 (0.117), 5000 -> +0.86 (0.093),
  no gate -> +0.86 (0.093). All floor-met 20/20. So the gate's cost is almost entirely the small, fixed floor on what raises may spend
  in early runs, where no headroom has been banked.
- Selection rule fixed before touching reserved seeds: highest lift with floor met 20/20 and min margin >= 0.10 -> `gate_min3000`.
- **Reserved confirmation (1001-1010, run once):** `gate_min3000` +0.76pp (t CI 0.56..0.96, p=0.002, better in 10/10 worlds) —
  **but floor met only 9/10** (seed 1002: margin -0.015; seed 1008 only +0.017). No-gate behaves the same (+0.80, 9/10).
  L0 meets the floor 10/10 (min margin 0.14); no-op 7/10.
- **Reading:** the lift generalises; the floor safety does not fully. Seed 1002 is a thin-margin world (L0 margin only 0.14) and a fixed
  minimum allowance spends the same rupees regardless of how much margin exists. G8 should veto this but evidently did not: consistent
  with X3.3's finding that projected spend is 1.5-4x too low, so G8's projection is optimistic. A missed floor voids the score, so one
  miss in 10 is a real cost; `gate_min3000` is NOT yet safe to recommend as-is.
- The reserved seeds are now spent; a fresh untouched set (2001-2010) is needed for any further confirmation.

### Items 1b / X1 / floor margin / X5.1 (parallel work)
**1b (state-dependent minimum allowance)** built: `StateMin` + pure `state_min_allowance()` in `lib/switchable_policy.py`
(run 1: fixed `run1_min`; from run 2: `min(min_amt, cap_frac x banked headroom)`, never below the harness's 300). Tests: rule table,
monotone in headroom, identity (cap 0 / run1 300 == L0) both as a unit and end to end on a full simulation. Sweep over
run1_min {300,1500} x cap_frac {0.25,0.5,1.0} on fresh20 launched (120 sims); result pending.

**Floor-margin reporting**: `funnel.floor_status()` (uses the official scorer; test checks it equals `gpc.score.summarize`), X0.6 table
(floor met, mean/min margin, floor-safe offtake per arm), X2 tables already carry it. New `x3_market/x3_3_floor_view.py` (no sim):
marginal direct ROAS of each action type vs the mean floor 4.34:
cuts remove spend at marginal dROAS 1.25 (-3.09 vs floor) so they *raise* portfolio ROAS; budget raises add spend at 4.04 (-0.30 vs
floor, dilute); CPM raises 4.35 (+0.01, neutral). **This explains X2's "cuts are floor insurance"**: cuts are the harness's way of
paying for raises, not waste.

**X1 module scoring** (`x1_modules/x1_run.py`, `lib/recorder.py`, `results/x1_modules.md`). Recorder = L0 + `detect_shocks`, test
asserts identical proposals/outcome to `HTNToolsOnly`. Findings so far (dev6, hash `63196db22b74`):
- **X1.1 forecast:** the grid's live-bid spend forecast (`pred_spend_live`, what projections/guardrails use) over-predicts the realised week
  by ~1.7x even for campaigns with an untouched bid and no run-out (real/pred spend 0.60, revenue 0.51; ran-out campaigns 0.49).
  It over-predicts relative to the trailing 28-day realised spend too (median 1.65x), so it is not a budget-truncation artefact alone.
  dROAS forecasts are less wrong (tier A 6.9 predicted vs 6.0 real). Documented as "unconstrained (no budget cap)" in `grid.predict_cell`;
  candidate mechanism: it assumes the best slot the bid affords with certainty and full slot-1-equivalent reach, where the market
  gives slot *shares*. Mechanism NOT isolated; X3.1 dose-response is the test. (Note: this is the opposite direction to X3.3's
  marginal Δspend, which was under-projected: levels over-forecast, marginal moves under-forecast.)
- **X1.2 iota:** within-type correlation with truth ~0 (brand 0.02, competition 0.03, generic -0.07); type-level bias +0.12 brand
  (est 0.24 vs true eff 0.12) and +0.14 generic; competition fine (-0.04). No improvement with more data across runs 1-6.
- **X1.3 siblings:** the chosen leader has the highest true value per impression in 70% of clear markets and 56% of near-ties
  (expected value of chosen/best 0.92 and 0.88). Better than chance for 2-3 siblings but far from reliable.
- **X1.4 headroom:** banked headroom grows 0 -> 6.6k INR/day over runs but the allowance is its min/20% slice (300 -> 966, then all
  of it in run 6); 2.7k shipped in run 6. End-of-window unused slack is 46-105k INR per world (end margin 0.24-0.54 ROAS points):
  the quantified opportunity behind the gate result.
- **X1.5 precheck:** 442 proposed = 442 shipped (guardrails block nothing after precheck); precheck dropped 130. False-negative side
  (would the guardrails have blocked the dropped ones?) is not measured.
- **X1.6 shocks (seed 7 so far, other seeds running):** OSA drop recall 1.0 / precision 1.0; price shock recall 0.25, precision 0.06 (31 flags
  elsewhere); demand shock recall 0.10. First detection is always 7 days after onset (the detector's recent window).
  Caveat: a price shock also moves reach; "elsewhere" flags may be real side-effects, not errors.

**X5 scripted LLMs** (`lib/scripted_llm.py`, `lib/arms.py::llm_factory`, `run_x51.sh`): modes always_yes/always_no/random/oracle per leaf;
`DayAwareHarness` sets the day for the L2 oracle. Bug caught by the prompt-template tests: numeric regexes swallowed the trailing period
("INR 200.0."), which `leaf()` would have absorbed silently as a default. Fixed (3 tests pass on the REAL prompt templates).
First oracle run (seed 7, default params, depth L2): calls L3 24, L2 4, L1 2, L6 1, L4 0 (explore disabled by default): most leaves
barely trigger at default params (X5.2). 180 sims queued (default + recalibrated params), result pending.
Machine load reached 43 on 10 cores with 3 batches; runs take ~110 s instead of ~60 s. Results are deterministic so only time is affected.

**X1.6 final (all 6 dev worlds):** OSA drop: recall 1.00, precision 1.00 (24/24 cell-runs), detected 7 days after onset in all 6 worlds.
Price shock: recall 0.43, precision 0.08 (19 TP, 208 flags elsewhere, 4 before onset); first detection 7 days after onset in 5 worlds, 14 days in
one. Demand shock (+15%): recall 0.12, precision 0.25 (14 TP, 105 missed): a 15% demand rise is mostly below the 2.5-sigma threshold.
Lead time is the detector's 7-day recent window, so 7 days is its floor. Implication for L2/L3 leaves: shock leaf triggers will be
dominated by false positives for price (and misses for demand) unless thresholds change. Caveat: price shocks also move reach, so some of the
208 "elsewhere" flags may be real side effects of the injected shock.

### Parallel build while batches run (CPU load 40+, so only code and tests; heavy runs queued behind the batches)
- `lib/scenarios.py`: 7 one-change value variants of dev (ι x1.3/x0.7, auction sigma 0.2/0.45, appeal rotated, intent x1.25/x0.8),
  files in `experiments/scenarios/`, plus harness_eval P1-P6 shock worlds (13 worlds). Test: each variant changes exactly one thing,
  dev file untouched, a perturbed world builds with the new value. `run_x73.sh` (5 arms x 13 worlds x seeds 303-305 = 195 sims) and
  `x7_generalisation/x7_run.py` written; queued to start when the other batches finish.
- `x3_market/x3_1_bid_dose.py` (X3.1): bid -50..+50% for 12 cells (4 per keyword type, tiers A/B) at seed-7/11 run-3 state, vs the grid's
  per-step predictions. Bug found by its test: `simulate_week` needs an empty frame, not None, for step 0; fixed. Test asserts step 0 equals the
  unmodified week and that spend and slot-1 share are monotone in bid. Queued (`run_x31.sh`).
- `EXPERIMENT_DESIGN.md` written (questions, metrics, seed hygiene, limits per experiment, how to run).
- Monitoring: one persistent monitor reports the test run, the 1b sweep and the X5.1 batch as each finishes.
- Test suite: 23/23 passed (7m19s under load 40+) including the X1 smoke test, recorder, scripted-LLM and floor_status tests. The perturbed-scenario and
  bid-dose tests (added after that run started) passed individually: 25 tests in total. Re-run the full suite once the batches finish.

### Constraints workaround plan (plan only, no implementation): `runtime_constraints_workaround/PLAN.md`
Inspected market/observation/score/incrementality code plus 4 read-only probes. Main points:
- C1 no clicks: keep the real funnel; add a share/position/conversion/cannibalisation decomposition (X0.4 v2). Shadow click layer rejected
  as default (it would be a different simulator with invented parameters).
- C2 impression share: NOT fully invisible. The public search prior gives slot-1-equivalent share nearly as well as the hidden affinity
  (sd 0.179 vs 0.174); error ~+-15%, breaks in demand-shock weeks. Proposes X1.7 (estimator accuracy) and X3.1 v2 (dose-response in share units).
- C3 offtake vs direct-ROAS floor, hidden ι: cannibalisation explains only ~9% of organic variance and ads/organic share causes (OSA,
  weekend), which explains X1.2's ~0 correlation and upward bias. Proposes the offtake-vs-margin frontier (3b, no sims), an oracle-ι arm
  (3d, value of information), estimator fixes (controls, organic_rank prior), then dither/IV and geo holdout only if worthwhile.
- Versioning: add EXPERIMENT_VERSION to results, per-version results folders; v1.1 (analysis-only), v2 (~50-100 sims), v3 (policy-side).
- W0: the plan's "+0.82%" is the old runtime report (commit 0b73557); now +0.23% (commit 483ea9e). Hypothesis: the "sizing overshoot" fix
  made L0 respect its allowance, i.e. removed most of what our no-gate arm adds back (+0.86pp). Testable by running 0b73557 in a worktree.

### W0 setup (old vs new harness)
- `git diff 0b73557 483ea9e`: `gpc/` identical; harness differs in sizing (μ-bisection -> greedy ratio knapsack), headroom (new 300 INR/day min
  allowance), policy (precheck before sizing), config/params, LLM methods, meter, trace. So market + baseline are the same, a paired comparison is valid.
- The old sizing code itself documents the mechanism: when even the tightest μ overshot the allowance it "gave up and shipped the whole
  unconstrained set" (the fix note measured 17-114x the allowance). Hypothesis: old L0 ≈ today's no_headroom_gate arm.
- Worktree `Ads-etal/w0_old_harness` at 0b73557 (detached; live tree untouched, verified `git status`). Import check: from the worktree the
  runner loads the old harness (μ sizing present, no min-allowance param).
- `experiments/w0/w0_sim.py` (standalone; imports only gpc/harness so it runs against the old code; drops traces before pickling since they hold
  old-harness objects), `experiments/w0/w0_run.py` (paired analysis vs cached l0/baseline/no_op/no_gate; ASSERTS the old worktree's seed-7 baseline
  equals today's exactly, otherwise the comparison is invalid). `run_w0.sh` queued behind the 1b and X5.1 batches (gate verified to match them).

### 1b sweep result (fresh20, 303-322, cuts kept, vs L0; `results/x2_ablation_state_min.md`)
| arm | vs L0 | t95 | floor | min margin |
|---|---|---|---|---|
| sm_r300_c0.25 / c0.5 / c1.0 | +0.02 / +0.13 / +0.28 | | 20/20 each | 0.201 |
| sm_r1500_c0.25 / c0.5 / c1.0 | +0.30 / +0.41 / **+0.53** (0.45..0.61) | | 20/20 each | 0.220 / 0.212 / **0.193** |
| gate_min1000 / 2000 / 3000 (fixed) | +0.41 / +0.70 / +0.80 | | 20/20 each | 0.210 / 0.148 / 0.117 |
| no gate | +0.86 | | 20/20 | 0.093 |
Reading: the state-dependent minimum keeps L0's own margin (~0.2) and recovers up to ~60% of the no-gate gain; the run-1 minimum is the
strongest single lever (r1500 vs r300). At equal lift the fixed and state-dependent minimums are on the same frontier (min1000 +0.41/0.210 vs
sm_r1500_c0.5 +0.41/0.212): state-dependence only pays off where a fixed minimum would spend through thin-margin worlds, which fresh20 has few of.

**PRE-REGISTERED confirmation (written before any 2001-2010 run):** arms no_op, l0, sm_r1500_c1.0, gate_min2000 on seeds 2001-2010, run once.
Success for a candidate = floor met 10/10 AND mean lift vs L0 > 0 with t-CI excluding 0. If both succeed, prefer the one with higher min margin
unless its lift is lower by > 0.2pp. Diagnostic (NOT confirmation, seeds already spent): sm_r1500_c1.0 and gate_min2000 on 1001-1010, to see
seed 1002 (thin margin) specifically.

### 1b sweep result (fresh20, 120 sims, hash `63196db22b74`) and a monitor bug
State-dependent minimum allowance (min_amt 3000; run1_min x cap_frac), vs full L0:
sm_r300_c0.25 +0.02 | r300_c0.5 +0.13 | r300_c1.0 +0.28 | r1500_c0.25 +0.30 | r1500_c0.5 +0.41 | **r1500_c1.0 +0.53 (CI 0.45..0.61, 20/20 better)**.
Floor met 20/20 in every arm; min margin 0.19-0.22 (L0 0.20), i.e. as safe as L0, unlike fixed gate_min2000 (+0.70, margin 0.148) or
gate_min3000 (+0.80, 0.117). So the state-dependent rule trades about 0.2-0.3pp of lift for keeping L0's margin.
The pre-registered selection rule (highest lift with 20/20 and margin >= 0.10) would still pick the fixed minimum on fresh20, but that rule never
saw the reserved-seed miss, so it is not the right criterion alone. Next: diagnostic on the (spent) seeds 1001-1010 incl. thin worlds 1002/1008
(sm_r1500_c1.0, sm_r1500_c0.5, gate_min2000; running), then one confirmation on new seeds 2001-2010 with l0 / no_op / gate_min2000 / best sm arm.
Issue found: my combined monitor printed "ALL DONE" while X5.1 was at 32/180 (shell loop condition bug; the first clause was always true when
a=b=1 only checked partially). Fixed by using one flag per job. No data affected.

### 1b diagnostic on the spent seeds 1001-1010 (not a confirmation)
| arm | vs L0 | floor met | min margin | seed 1002 | seed 1008 |
|---|---|---|---|---|---|
| gate_min2000 | +0.70 (0.51..0.88) | 10/10 | +0.047 | +0.062 | +0.047 |
| gate_min3000 | +0.76 | 9/10 | -0.015 | -0.015 | +0.017 |
| **sm_r1500_c1.0** | **+0.42 (0.31..0.53)** | **10/10** | **+0.119** | +0.119 | +0.195 |
| sm_r1500_c0.5 | +0.33 (0.23..0.43) | 10/10 | +0.118 | +0.118 | +0.207 |
| L0 | 0 | 10/10 | +0.140 | +0.140 | +0.234 |
The state-dependent minimum protects the thin-margin worlds (1002: +0.119 vs L0 +0.140) while keeping about half of the fixed minimum's gain.
Fixed 2000 survives but with almost no margin (0.047).
**Pre-registered confirmation (new seeds 2001-2010, run once):** recommend `sm_r1500_c1.0` only if floor met 10/10 and its lift CI is above 0;
`gate_min2000` and `gate_min3000` are comparators (reported, not recommended). Launched with l0 and no_op.

### Coordination note (this session)
A second session is working in the same `experiments/` tree (added round-2 STATE_ARMS c2.0/c4.0/r3000, ran the 1001-1010 diagnostic, and is running the
2001-2010 confirmation with no_op/l0/gate_min2000/gate_min3000/sm_r1500_c1.0). Its pre-registration (sm_r1500_c1.0 recommended only if floor 10/10 and CI > 0)
is compatible with mine above. To avoid duplicate CPU on an overloaded machine (17 sim processes, load 70-110), this session cancelled its own queued
`run_1b_confirm.sh` before it ran anything; results come from the other session's run (same arm names and code hash, so same cache keys).
This session still owns: X5.1 (139/180), W0 (old vs new harness), X7.3, X3.1.

### Snapshot report
`presentations/measurement-experiments-snapshot.md`: status of every experiment, headline numbers, corrections, limitations, decisions ahead.
Includes an INTERIM X5.1 table on the 4 seeds every arm has (7/11/23/42): no leaf adds offtake, even oracle; L6 always-veto -0.043 (default)
/ -0.121 (recal), CI excludes 0; L4 explore and all-leaves arms lean negative; scripted answers per world L1 ~3-4, L2 ~6, L3 ~31, L6 ~1-2, L4 ~30
(recal); no fallbacks. To be replaced by the 6-seed table when the batch completes.

### 1b round 2 (this session) and coordination
- Round 1 (r300/r1500 x cap 0.25-1.0) was still rising at the upper edge, so round 2 ran run1_min {1500, 3000} x cap {2, 4} on fresh20 (80 sims):
  sm_r1500_c2.0 +0.605 (margin 0.183), sm_r1500_c4.0 +0.637 (0.150), sm_r3000_c2.0 +0.719 (0.147), **sm_r3000_c4.0 +0.746 (0.142)**, vs fixed
  min2000 +0.698 (0.148) and min3000 +0.800 (0.117). All floor 20/20. Larger run-1 minimum and looser cap trade margin for lift along a
  frontier that the fixed minimum sits on too; state dependence is about *where* spend goes (thin-margin worlds), not extra free lift.
- Tests added: `state_min_allowance` rules (run 1 fixed, cap by banked headroom, monotone), identity case, and an end-to-end check that
  `cap_frac=0, run1_min=300` reproduces L0 exactly. Suite green at each step.
- Two sessions launched overlapping confirmations on 2001-2010. Mine (`run_confirm2000`) was killed after 14/50 because 4 of its 5 arms
  duplicated the other session's pre-registered run (same arm names, hash, cache keys). The other session's pre-registration
  (`sm_r1500_c1.0` recommended only if floor 10/10 and CI > 0) is the **primary** confirmation. My extra candidate `sm_r3000_c4.0` runs on
  2001-2010 after it, plus the spent 1001-1010 as a labelled diagnostic. Reporting it alongside, and counting it as a second candidate
  (two candidates on one confirmation set: any "win" for either is read with that in mind).

### X5.1 / X5.2 result (180 sims, dev6, depth L2, scripted leaves, $0; `results/x5_llm_aided.md`)
- **No leaf beats L0 in any mode, including the truth-reading oracle.** L1/L2/L3 at default params: all within ±0.06pp, every t-CI includes 0.
- **L6 review veto costs offtake:** always-veto -0.056pp (6/6 worse, p=0.031), oracle-veto -0.030, random -0.015. Under the current gate the few large
  raises that reach review are worth keeping. Recalibrated threshold 300: always-veto -0.140, oracle -0.061.
- **L4 explore (recal: 5 cells, 1000 INR/day):** always-yes -0.07, random -0.10, oracle -0.03 (CIs wide, none positive on average).
- All-leaf arms: always-no ≈ 0 (= L0, as designed), always-yes -0.06 (default) / -0.24 (recal), oracle -0.05 / -0.12.
- **Triggers (X5.2), calls per 6-run simulation, all-leaf oracle arm:** L3 60, L2 12, L1 3.7, L6 2.5 (default); with recal also L4 60, L6 5.8.
  So L1 and L6 fire less than once per run; L3 fires ~10 times per run but only on near-ties, where the choice barely matters (X1.3: value ratio 0.88).
- Floor met 180/180; 0 fallbacks; margins unchanged (~0.24).
- **Reading:** while the headroom gate binds, the leaves act on a sliver of decisions (mostly raises the gate already throttles), so even perfect
  answers can't move offtake. The paid slice (X4.2/X5.3) is NOT justified for these leaves at current settings. Worth re-testing only after a gate
  relaxation (more raises -> more L1/L6 decisions).
- **Limitation:** the oracles are proxies (L1/L4 use true value per slot-1 impression / CPM; L6 uses the starting bid as CPM, no live CPM in its
  prompt; L2 knows the injected demand shocks only). A better oracle could do better; these are not tight upper bounds.
- Note on the table: `calls_per_world` in the main table counts all leaf calls attempted, including defaulted ones from unscripted leaves.

### 1b confirmation result (seeds 2001-2010, run once by the other session; read from the shared cache by this session)
| arm | vs L0 | t95 | p | worse/better | floor | min margin |
|---|---|---|---|---|---|---|
| sm_r1500_c1.0 | **+0.32** | 0.23..0.41 | 0.002 | 0/10 | **10/10** | 0.287 |
| gate_min2000 | +0.38 | 0.29..0.48 | 0.002 | 0/10 | 10/10 | 0.286 |
| gate_min3000 | +0.45 | 0.32..0.57 | 0.002 | 0/10 | 10/10 | 0.282 |
| no_op | -0.12 | -0.21..-0.02 | | 8/2 | 9/10 | -0.027 |
| L0 | 0 | | | | 10/10 | 0.304 |
- **Pre-registered criteria met for sm_r1500_c1.0** (floor 10/10, CI above 0). Under this session's tie-break (prefer higher min margin unless lift
  lower by > 0.2pp) it is preferred over gate_min2000 (margin 0.287 vs 0.286, lift gap 0.06pp), and it is the arm that protected thin world 1002
  (margin 0.119 vs 0.047 for gate_min2000, -0.015 for gate_min3000; 1001-1010 diagnostic).
- 2001-2010 are all roomy worlds (L0 min margin 0.30), so they cannot discriminate safety; lift is smaller than on fresh20 (+0.32 vs +0.53).
- **Recommendation (for the harness owner, not applied):** state-dependent minimum allowance, run1_min 1500 INR/day, then min(3000, 1.0 x banked
  headroom/day) from run 2. Expected +0.3..+0.5pp offtake over current L0 with L0-level floor margin. Untested on the eval scenario's values (X7.3 pending).

### X5.1 / X5.2 final (6 dev worlds, 180 sims, $0; `results/x5_llm_aided.md`)
- No leaf adds offtake in any mode, including oracle. Best arm per leaf = the passive answer (0.000) or noise (L3 random +0.021, CI -0.012..0.054).
- Leaves that veto/redirect raises cost offtake: L6 always-veto -0.056 (default, p=0.031, 6/6 worlds worse) and -0.140 (recal, p=0.031);
  L6 oracle -0.030 / -0.061; L4 explore (recal) -0.03..-0.10 (wide CIs); all-leaves always-yes -0.063 (default) / -0.235 (recal), both p=0.031;
  all-leaves oracle -0.050 / -0.123.
- Floor met 6/6 in every arm; 0 fallbacks.
- Scripted answers per world (X5.2): default L1 1.8, L2 5.9, L3 30, L6 1.3 (L4 off); recal L1 1.9, L2 3.8, L3 29, L4 30 (5/run cap), L6 2.9.
  L1/L2/L6 fire too rarely to matter whatever they answer; L3 fires often but leader choice doesn't move offtake.
- Fix in my analysis: the trigger table summed two arms (double counting); now the mean. A second slip (a comment placed before `.reset_index()`
  dropped the index columns) caught on the rerun and fixed.
- Reading: as configured, real LLM calls cannot be expected to move offtake; the paid slice should not run until triggers/decisions change.
  Caveat: oracle answers are proxies from truth, not optimal answers.

### X5.1 final, 1b confirmation, tally and report updates
- **X5.1/X5.2 final (180 sims, 6 dev worlds):** no scripted leaf improves offtake. Oracle vs L0: L1 0.000, L2 -0.000, L3 -0.002, L6 -0.030 (default) / -0.061 (recal), L4 -0.033;
  always-veto L6 -0.056 / -0.140; all-leaves always-yes -0.063 / -0.235, oracle -0.050 / -0.123. Best arm: L3 random +0.021 (CI -0.012..0.054). Floor met everywhere, 0 fallbacks.
  Answered calls per world: L3 ~30, L4 ~30 (recal), L2 ~6 (4 recal), L1 ~2, L6 ~1 (3 recal).
  Two reporting bugs found by cross-checking against the presentations snapshot: `calls_per_world` counted defaulted calls of unscripted leaves (now answered vs defaulted), and the trigger
  table summed two arms instead of averaging (L3 read 60 instead of 30; a parallel session fixed the same line concurrently, so shared files can change under me).
- **1b confirmation (seeds 2001-2010, run once, rule pre-registered): PASSED.** `sm_r1500_c1.0` +0.32 (0.23..0.41), 10/10 better, floor 10/10, min margin 0.287 (L0 0.304).
  Comparators: fixed 2000 +0.38 (10/10 floor), fixed 3000 +0.45 (10/10 floor). Caveat: no thin-margin world in this set (L0 min margin 0.30). Over all unseen sets fixed 3000 has 1 floor miss in 20.
  Another session also ran extra state-min arms on the tuning seeds; only `sm_r1500_c1.0` is the pre-registered, confirmed arm.
- **Tally** (`runtime_findings/PRESENTATION_TALLY.md`, written by the parallel session, rows D1/D3 filled and D4, G1-G3 added by me): the older decks' +0.82% is labelled PENDING W0, not edited.
  `presentations/measurement-experiments-snapshot.md` updated with the final X5.1 numbers and the confirmation (statuses, §1, §2, §8, §9, §12).
- **Updated:** `runtime_findings/FINDINGS.md` (§8b, §9, §10, §11), `NEXT_STEPS.md`, new `experiments/RESULTS.md`, `runtime_feedback_improvement/RUNTIME_FEEDBACK_REPORT.md` (addendum §7, revision 2 left intact),
  results bundle `runtime_findings/results/`. Pending: X7.3, X3.1 (queued behind other batches), W0 (other session).
- Seed hygiene note: a parallel session ran an extra arm (`sm_r3000_c4.0`, chosen after seeing results) on seeds 2001-2010 and 1001-1010. Seeds 2001-2010 are therefore no longer
  untouched for any arm other than the pre-registered `sm_r1500_c1.0`; any further confirmation needs a new reserved set (suggest 3001-3010, untouched).
- CPU freed (load ~6), so X7.3 (now 6 arms incl. `sm_r1500_c1.0` x 13 worlds x 3 seeds = 234 sims) and X3.1 (seeds 7, 11 run 3) were started directly instead of waiting on the
  other session's batches.
- **Correction (X5.2 trigger counts):** my trigger table summed the all_oracle and all_always_yes arms, doubling every count. Correct calls per
  6-run world (all-leaf oracle, default params): L3 30.7, L2 6.0, L1 1.8, L6 1.3 (recal: L4 30, L6 2.9). Found by comparing with the other session's
  tally. `x5_run.py` fixed (one arm only); results file regenerated. The X5.1 lift table and conclusions are unaffected.

### 1b confirmation result and tally (2001-2010 run once; 1001-1010 diagnostic)
`results/x2_ablation_confirm2000.md`, `x2_ablation_diag1000.md` (copied to `runtime_findings/results/`). Full suite **25/25 pass** (317 s under load).
- 2001-2010 (vs L0): sm_r1500_c1.0 **+0.32 (0.23..0.41)** floor 10/10, min margin 0.287; fixed 2000 +0.38 10/10; sm_r3000_c4.0 +0.43 10/10;
  fixed 3000 +0.45 10/10. No-op misses the floor in 1/10. **Pre-registered test for `sm_r1500_c1.0` passed.**
- 1001-1010 diagnostic: sm_r1500_c1.0 +0.42, floor 10/10, min margin 0.119; sm_r3000_c4.0 +0.62, 10/10, 0.057; fixed 2000 +0.70, 10/10, 0.047;
  fixed 3000 +0.76, **9/10**, -0.015. Over the 20 unseen worlds: sm_r1500_c1.0 20/20 (min margin 0.119); fixed 3000 19/20.
- Caveats recorded: 2001-2010 had no thin-margin world (L0 min margin 0.30); lifts there are smaller for every arm; two candidates shared
  one confirmation set. Recommendation unchanged: state-dependent minimum (`sm_r1500_c1.0`), expected +0.3 to +0.5pp at L0's margin.
- Tallied with the other docs: the presentations snapshot, `experiments/RESULTS.md` and the runtime report addendum already carried the
  same +0.32/+0.38/+0.45 numbers (written by the other session); added to the snapshot the 20-world tally table and the second candidate,
  and to `runtime_findings/FINDINGS.md` §9 and `NEXT_STEPS.md`. No contradictions found between the documents.
- Process: my duplicate confirmation job was killed (14/50) to avoid redundant CPU; only the unique arm ran afterwards (20 sims).

### W0 result: old (0b73557) vs new (483ea9e) harness, dev6, paired (`results/w0_old_vs_new_harness.md`)
- Validity: gpc identical; the old worktree's seed-7 baseline equals today's exactly (assertion passed).
- **Old L0 vs baseline +0.824% (t 0.55..1.10), reproducing the runtime report / paper's +0.82% exactly**; per seed 101 +0.936, 202 +1.116 (paper:
  +0.94 / +1.12). So the old number was right for the old code; our measurement agrees with the earlier one.
- **New L0 vs baseline +0.234%. The 483ea9e fixes cost -0.59pp offtake** (old vs new L0 +0.589, CI 0.40..0.78, 6/6 seeds); old spends +7.0% more.
- Old L0 met the floor 6/6 (min margin 0.227 vs new 0.244). Old L0 sits between new L0 and no-gate (-0.26pp vs no_headroom_gate): its sizing
  overshot the allowance (17-33x per the critique) but the allowance was not irrelevant.
- **Reading:** the fix made sizing correct (respect the allowance), and that correctness is exactly what costs the 0.59pp, because the allowance itself
  is too tight (X1.4: 46-105K INR unused slack). The state-dependent minimum (sm_r1500_c1.0, +0.32..+0.53pp, floor-safe incl. thin seed 1002) recovers
  most of the old lift while keeping the fix. On dev6 the old overshoot was never punished by the floor; whether it would be on thin-margin worlds is
  untested for the old code (it was the fixed-3000 arm that missed on seed 1002).

### W0 result (old 0b73557 vs new 483ea9e harness, dev6; `results/w0_old_vs_new_harness.md`)
- Guard passed: the old worktree's seed-7 baseline equals today's exactly (same gpc).
- Old L0 vs baseline **+0.824%** (t-CI 0.55..1.10), reproducing the runtime report / paper rev 5 / deep dive §11.5 exactly, per seed
  (0.355, 0.699, 0.887, 0.950, 0.936, 1.116). New L0 +0.234%.
- **Old L0 vs new L0: +0.589pp** (0.40..0.78, p=0.031, 6/6 seeds); old spends +7.0% more (5.4..8.6). Old floor met 6/6, margins 0.23-0.60
  (new 0.24-0.54; not uniformly thinner).
- Old L0 vs no-gate: -0.255pp (-0.36..-0.15). The old harness sat ~70% of the way from today's L0 to no gate: its sizing ignored the allowance
  only in runs where the raise set overshot (the "give up and ship everything" branch), and had no run-1/2 raises (allowance 0).
- **Conclusion:** the drop from +0.82% to +0.23% is caused by the 2026-10-03 harness fixes, mainly enforcing the headroom allowance (F1). That fix
  traded ~0.6pp of offtake for floor safety in these worlds without any observed floor miss before it (old harness met the floor in 6/6 dev
  worlds; its safety on thin-margin worlds like seed 1002 is untested).
- Docs updated with W0 (this session): `runtime_findings/FINDINGS.md` new §12 (and the duplicate "## 9" heading renamed §8c, content untouched);
  `PRESENTATION_TALLY.md` rows A1-A3 (holds, changed since: +0.824% reproduced exactly from 0b73557); `RUNTIME_FEEDBACK_REPORT.md` addendum headline row;
  `experiments/RESULTS.md` W0 row and result 5. The other session had already filled the X5/1b rows in these files; only W0-dependent text was changed.

### Recommendations consolidated
`runtime_findings/recommendations/` (README priority table, `01-harness-changes.md`, `02-llm-layer.md`, `03-next-experiments.md`,
`04-measurement-practice.md`) gathers every recommendation from FINDINGS, NEXT_STEPS, the snapshot, the tally and the runtime report
addendum. Content taken from existing results only; nothing new was run.

### Recommendations collected
`runtime_findings/recommendations/RECOMMENDATIONS.md`: 12 recommendations (R1-R12) with evidence, status (confirmed / supported / pending / hypothesis),
owner and priority. P0: state-dependent minimum allowance (pending 1b confirmation), keep cuts, read the F1 sizing fix as a ~0.6pp trade-off (W0).
Harness-side items are addressed to the session that owns `harness/`. To be updated when the running experiments finish.

### Recommendations folder; decision on older decks
- Decision: older decks stay untouched until W0 settles +0.82% vs +0.23%. Recorded in `runtime_findings/PRESENTATION_TALLY.md`.
- **Correction (same turn):** I wrote ten recommendation files into `runtime_findings/recommendations/` and a `README.md` there, not noticing that a second session had created
  the folder seconds earlier (`RECOMMENDATIONS.md` R1-R12 plus `01-harness-changes.md`, `02-llm-layer.md`, `03-next-experiments.md`, `04-measurement-practice.md`). My `README.md` **overwrote theirs**
  (a priority table). My ten files duplicated their R1-R12, clashed on file numbers and called W0 pending after it had reported, so I deleted them and rebuilt `README.md` from the summary table in
  `RECOMMENDATIONS.md`, with a provenance note saying so. The second session's files were not changed. Lesson: list a shared folder before writing to it; shared files here change under me.
- **W0 has reported** (16:58, by the other session): the pre-fix harness reproduces +0.824% exactly vs baseline; today's gives +0.234% (old minus new +0.59pp, 6/6 seeds, 7% more spend, floor met 6/6).
  Older decks are still untouched; whether to add a correction note is the user's decision (asked).

### X3.1 bid dose-response result (this session; seeds 7 and 11, run-3 state, 12 cells each, steps -50..+50%)
- **Grid over-forecast mechanism supported:** at the live bid the grid predicts ~1.6-2.4x the realised spend (real/pred 0.44-0.63 by keyword type,
  both seeds); the gap closes as the bid rises (+50%: 0.68-1.14). Consistent with the grid assuming the best affordable slot is won with certainty,
  where the market gives a share of auctions; the two agree only when the bid wins almost every auction. Explains X1.1's ~1.7x level gap.
- **Response is steep near the live bid:** -10% bid cuts cell spend 39-74% (brand seed 7: 4.0k -> 1.0k INR/week); +10% raises it 27-52%.
- **Marginal offtake per rupee of a +10% raise:** brand 0.75 / 0.42, generic 0.58 / 0.46, competition -0.03 / -0.25 (seed 7 / 11). At +50% it turns
  negative for brand and generic in seed 11 (-0.12, -0.16). Candidate causes (not isolated): a bigger raise on a budget-bound campaign exhausts the budget
  earlier and truncates the campaign's other keywords; own-sibling displacement in the same market. Raising competition-keyword bids returned ~0 or
  negative offtake in both seeds despite high true incrementality.
- Brand: marginal direct ROAS 17-22 but marginal offtake per rupee <= 0.75: direct ROAS overstates the value of brand raises by ~25x (cannibalisation).
- Fix: `real/pred_spend` showed `inf` where the grid predicts 0 spend at a low bid (no slot); now NaN. Added `--from-csv` to re-analyse without
  re-simulating; both seeds regenerated; dose test passes.
- Implications for recommendations: supports R4 (calibrate projections; the over-forecast is a share-vs-certainty issue, largest at the live bid);
  suggests raise sizes should be small (the marginal return falls fast past +10-30%) and that competition-keyword raises deserve scrutiny.

### W0 thin-world diagnostic (old harness 0b73557 on seeds 1001-1010; diagnostic only, these seeds are spent)
- Old L0 vs today's L0: **+0.44pp** (t-CI 0.31..0.57), floor met **10/10**, but margins only **0.050 (seed 1002)** and **0.057 (seed 1008)**
  (today's L0: 0.140 / 0.234).
- Same worlds: state-dependent min `sm_r1500_c1.0` +0.42pp with margins 0.119 / 0.195; fixed min 3000 +0.76pp, 9/10 (1002 at -0.015).
- Reading: the pre-fix harness did not miss the floor here but came within ~0.05 ROAS points of it twice, so the F1 fix bought real safety margin
  in thin worlds. **The recommended state-dependent minimum recovers about the old harness's lift (+0.42 vs +0.44pp) while keeping 2-3x its
  margin where margin is thin.** Supports R1 and R3: the choice is a point on the offtake-vs-margin trade-off, and R1 sits on a better point than
  either the pre-fix behaviour or a fixed minimum.

### X3.1 bid dose-response (seeds 7 and 11, run 3, 12 cells each: 4 per keyword type, tiers A/B; `results/x3_1_bid_dose_seed{7,11}_run3.*`)
- **The grid's level over-forecast replicates and has a visible shape.** At the live bid, real/pred weekly spend is 0.44 / 0.63 / 0.45 (seed 7) and 0.57 / 0.65 / 0.42 (seed 11)
  for brand / competition / generic. At +50% it is 0.94 / 0.88: the grid is right only when the cell clears its slot with certainty.
- **Real spend is smooth and monotone in bid (12/12 cells, both seeds); the grid's prediction is a step function** (about 3 distinct predicted values across 7 bid steps per cell;
  it predicts 0 at -30%, where real spend is 6.8k-7.9k INR). Cell-level correlation of slot-1 share with real/pred at the live bid: 0.89 (seed 7) but 0.44 (seed 11).
  **Mechanism: supported, not isolated** (the grid assumes the affordable slot with certainty; the market gives shares), since slot-1 share explains the gap well in one seed and only partly in the other.
- **Marginal offtake by type (consistent across both seeds):** generic raises pay modestly (+10%: +5.2k / +2.3k offtake) with diminishing or negative returns by +50% (seed 11: -1.9k);
  generic cuts lose a lot (-50%: -19.6k / -15.8k); **competition moves lose offtake in both directions** (raising: -0.2k..-2.7k; cutting: -0.9k..-12.2k), so the live bid is near its optimum;
  brand has no consistent sign (seed 7 positive, seed 11 ~0 or negative). Cell-level offtake responses are noisy; spend and slot share are clean.
- **Cross-check from X3.3 by keyword type** (321 shipped actions, no new sim): cuts on **generic** keywords are 167 of the 250 cuts and lose **0.90 offtake per INR** (marginal dROAS 1.83); cuts on
  competition lose 0.36 per INR (marginal dROAS 0.28); brand cuts move little spend (-1.0k) and offtake is, if anything, higher (+4.5k). Raises on generic return **3.20** offtake per INR (34 actions).
  Hypothesis: if cuts exist to buy floor margin, cutting competition and brand before generic buys more margin per offtake lost.
- **Exploratory arm `no_generic_cuts`** (M_Base cuts skip generic keywords; new `generic_cuts` switch, test asserts it removes exactly the generic cuts and keeps the rest, non-vacuously at run 4)
  launched on fresh20 (tuning seeds, so any gain needs confirmation on new seeds 3001-3010 before it is believed). The strengthened test passes.

### Exploratory arm `no_generic_cuts` (fresh20, tuning seeds): hypothesis NOT supported
Motivated by X3.3/X3.1 (generic cuts lose 0.90 offtake per INR vs 0.36 for competition). Result vs L0: **+0.09pp** (t-CI 0.01..0.17, 13 better / 7 worse), but the floor is met in only **19/20** worlds
(min margin -0.003) and the mean margin falls from 0.394 (L0) to 0.181, close to removing all cuts (no_cuts: +0.05pp, floor 18/20, mean margin 0.076).
Reading: most cut spend is generic, so generic cuts carry most of the floor insurance; skipping them buys a tiny, unsafe gain. Not recommended, and not worth a confirmation set.
The narrower idea (cut competition/brand *first*, keep generic cuts as the fallback) is a reordering, not a removal, and remains untested.

### X3.1 result: bid dose-response (12 cells x 7 steps, seeds 7 and 11, run-3 state; `results/x3_1_bid_dose_seed{7,11}_run3.md`)
- **Cause of the grid's forecast error found.** The grid's predicted spend/revenue is identical for every raise step (+10/+30/+50%) and equal to its
  live-bid prediction: it treats a bid at or above the median clearing CPM as winning slot 1 with certainty (`grid.slot_at_bid` takes the best slot
  whose *median* price the bid meets). The market gives a share: true slot-1 share at the live bid is 0.42-0.83 (by type and seed) and reaches ~1.0
  only at +30-50%, where real spend converges to the grid's number (real/pred 0.93-1.14).
- This single assumption explains both earlier module findings: **levels over-forecast ~1.7x (X1.1)** because the grid assumes full share today, and
  **marginal raises under-forecast 1.5-4x (X3.3)** because the grid predicts ~0 change for a raise that in fact buys the missing share.
- **Competition-keyword raises lower total offtake** in both seeds (-0.03..-0.25 offtake per INR) although their ad revenue rises (marginal dROAS
  0.5-1.4). Hypothesis (unverified): extra competition spend exhausts the campaign budget earlier and starves its better keywords. Generic raises
  have diminishing returns (0.58 -> 0.35 per INR on seed 7; negative at +50% on seed 11). Brand is noisy across seeds (low incrementality).
- Cuts: generic/competition cuts lose 0.5-0.9 offtake per INR saved; a -50% bid nearly empties the cell (slot-1 share 0.05-0.38).
- Limitations: 12 cells, 2 seeds, one run state, single week (no carry-over); sums over cells of a type.
- Implication for the harness owner (recommendation): price raises with the share curve (`gpc.market._slot_shares` logic is what the market uses; a
  policy can estimate the lognormal spread from its own slot-mix data) instead of the median-price step; exclude competition raises on budget-bound
  campaigns until the budget-starvation hypothesis is tested.

### X7.3 result (13 perturbed worlds x 3 seeds, 234 sims, hash `63196db22b74`)
`sm_r1500_c1.0` +0.51pp (0.41..0.61) over the 21 value-variant pairs and +0.57pp (0.46..0.69) over the 18 shock-world pairs, better in 39/39, **floor met 39/39**
(min margin 0.089 / 0.060 vs L0 0.113 / 0.065). Fixed 3000: +0.76 / +0.79, floor 38/39 (miss in V_intent_hi, margin -0.019); no-gate the same. No cuts: -0.03 / -0.02 and floor met only 12/18
in shock worlds (P2 and P4 3 misses each, min margin -0.277); no-op misses the floor in 7/18 shock pairs. L0 vs no-op +0.12 / +0.10. Gate relaxation gains 0.3-1.1pp in every world
(smallest V_intent_lo, V_sigma_hi). Caveat: 3 seeds per world, self-authored perturbations, CIs optimistic (clustered). Docs updated: FINDINGS §14, RESULTS.md, PRESENTATION_TALLY (G4),
RECOMMENDATIONS R1, snapshot rows.
Process issue: my X7.3 monitor never fired because `pgrep -f run_x73.sh` matched a stale shell from an earlier session whose command line contained that string; the job had finished.
Use a log-line condition instead of pgrep -f on script names.
- Full suite after all changes: **26 passed** (1m31s, machine idle). FINDINGS.md stale "pending" statements (sections 7, 9, 11, 8c caveat) updated to point at §13/§14; NEXT_STEPS updated.

### X7.3 result: perturbed worlds (13 worlds x seeds 303-305 = 39 pairs, 234 sims; `results/x7_generalisation.md`)
| family (pairs) | arm | vs L0 | t95 | floor met | min margin |
|---|---|---|---|---|---|
| value (21) | **sm_r1500_c1.0** | **+0.51** | 0.41..0.61 | **21/21** | 0.089 (L0 0.113) |
| value (21) | gate_min3000 / no gate | +0.76 / +0.79 | | 20/21 / 20/21 | -0.019 / -0.038 |
| value (21) | no_cuts | -0.03 | -0.13..0.07 | 21/21 | 0.007 |
| shock (18) | **sm_r1500_c1.0** | **+0.57** | 0.46..0.69 | **18/18** | 0.060 (L0 0.065) |
| shock (18) | gate_min3000 / no gate | +0.79 / +0.80 | | 18/18 / 18/18 | 0.012 / 0.009 |
| shock (18) | **no_cuts** | -0.02 | -0.14..0.10 | **12/18** | **-0.277** |
| shock (18) | no_op | -0.10 | | **11/18** | -0.312 |
- **The recommended state-dependent minimum generalises:** better than L0 in 39/39 pairs, floor met 39/39, per-world mean +0.32 (V_intent_lo) .. +0.74 (V_sigma_lo).
  Lift scales with how much headroom the world banks; margin stays close to L0's.
- Fixed 3000 / no-gate miss the floor in V_intent_hi (1/39 each): with the earlier seed-1002 miss, the fixed minimum has now voided the score in 2 of ~60
  unseen worlds.
- **Cuts are floor insurance, confirmed under shocks:** no_cuts misses the floor in 6/18 shock pairs (P2 price shock 3/3, P4 all-shocks-early 3/3) with no
  lift anywhere (-0.03 / -0.02). Never remove cuts.
- Doing nothing (no_op) misses the floor in 11/18 shock pairs: the floor is not passive; L0's cuts are what hold it under shocks.
- Caveat: the CIs treat 3 seeds within a world as independent though they share parameters (optimistic); perturbations are one-at-a-time, chosen by us.
- Monitor note: my "wait for X7.3/X3.1" monitors never fired because `pgrep -f "run_x73\.sh"` matched the monitor's own command text (same self-match trap
  as the earlier pkill). Data unaffected; checked the logs directly instead.

### Final doc pass (this session, 18:35)
- The other session had already written X7.3 into FINDINGS §14, tally G1-G4 and RESULTS. This session added: FINDINGS §15 (X3.1, mechanism identified, competition
  raises) and fixed §11; tally C5 verdict ("mechanism identified" rather than "supported, not isolated", with the flat-prediction evidence) and section E (snapshot
  re-check: numbers agree; status lines stale at lines 6, 20, 33-34, 60, 63, 208, 210, 238, 254, 256, listed with corrections; presentations not edited without
  the user's go-ahead); RESULTS X3.1 row; runtime report F8 row (X7.3) and a new "Grid forecast" row (X3.1).
- Concurrent-write check: after the runtime-report edit, both this session's W0 row and the new rows are present (the on-disk change was this session's own write).
- **Final test run: 26/26 passed** (92 s, machine idle) after all jobs and doc updates.

### X7.3 generalisation result (this session; 13 perturbed worlds x seeds 303-305 = 39 world-seeds per arm, 234 sims; `results/x7_generalisation.md`)
Worlds: 7 one-change value variants of dev (ι x1.3/x0.7, auction sigma 0.2/0.45, appeal rotated, intent x1.25/x0.8) + harness_eval P1-P6 shock worlds.
The batch included `sm_r1500_c1.0` (added to run_x73.sh by the parallel session); `x7_run.py` updated to report it.
| arm | shock family (18) | value family (21) | better | floor met | min margin shock / value |
|---|---|---|---|---|---|
| sm_r1500_c1.0 (R1) | +0.574 (0.46..0.69) | +0.509 (0.41..0.61) | 39/39 | **39/39** | 0.060 / 0.089 (L0 0.065 / 0.113) |
| gate_min3000 | +0.792 | +0.762 | 39/39 | 38/39 (V_intent_hi) | 0.012 / -0.019 |
| no_headroom_gate | +0.801 | +0.785 | 39/39 | 38/39 (V_intent_hi) | 0.009 / -0.038 |
| no_cuts | -0.021 | -0.028 | 15/39 | **33/39** (P2 x3, P4 x3) | -0.277 / 0.007 |
| no_op | -0.100 | -0.116 | 12/39 | 30/39 | -0.312 / -0.013 |
- **R1 generalises:** positive in every one of 39 perturbed world-seeds, floor met 39/39, min margin close to L0's own. Lift ranges by world from +0.32
  (V_intent_lo, V_sigma_hi) to +0.74 (V_sigma_lo).
- **Fixed minimum 3000 / no gate fail the floor again** in a world they were not tuned on (V_intent_hi): the second independent failure (after seed 1002).
- **Cuts-as-insurance strongly confirmed:** removing cuts gives no lift and misses the floor in 6 of 18 shock-world runs (P2 bigger price shock, P4 all
  shocks earlier). L0 with cuts meets the floor in all 39.
- The harness_eval P-worlds are no longer near-duplicates at 3 seeds: arm lifts vary by scenario (no_op -0.24..+0.05; R1 +0.32..+0.74).
- Caveat: pairs within a scenario share its parameters, so the pooled CIs are optimistic; 3 seeds per world.
- Process note: my completion wait never ended because `pgrep -f run_x73.sh` matched a stale monitor process from an earlier session (its command text
  contained the string); killed it. The batch itself finished cleanly (0 tracebacks).

### Round closed (this session)
- FINDINGS §14 (X7.3) and §15 (X3.1), the tally (no PENDING rows) and the runtime-report addendum were already written by the parallel session; I checked
  their X7.3 numbers against my own `x7_run.py` output: identical. Their X3.1 reading (grid predicts the same spend at every raise step) is sharper than mine
  and stands.
- Snapshot (`presentations/measurement-experiments-snapshot.md`) brought current: header, summary (W0, X7.3, X3.1), scorecard, §7 grid cause, §9 status,
  §11, §12. No "queued" items remain.
- RECOMMENDATIONS.md: R3 (thin-world W0 diagnostic) and R4 (X3.1 mechanism) updated.
- Full suite: **26/26 pass** (92 s).
- Remaining open (not started): X4, X6, paid LLM slice (not recommended as configured), RESULTS.md, constraints-plan v1.1/v2 items (frontier, oracle-ι,
  ι estimator, share estimator). The w0_old_harness worktree can be removed when no longer needed (`git worktree remove ../w0_old_harness`).
