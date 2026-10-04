# Runtime findings from the slice-and-dice experiments (2026-10-03)

Source: `experiments/` (measurement layer, 12 passing tests) run on the System 1 harness, dev scenario, 6 seeds
(search 7/11/23/42, held-out 101/202), paired under common random numbers. All runs cost $0 (no LLM).
Raw tables: `results/`. Narrative log: `../logs/2026-10-03-experiments-log.md`. Reproduce from `grid-path-challenge/`
with `PYTHONPATH=.:.. .venv/bin/python -m experiments.<x0_measurement.x0_run | x2_ablation.x2_run | x3_market.x3_3_action_effects>`.

**Code version:** all runs (including the 126 added later) are from hash `63196db22b74`, the live harness; earlier note: one older `l0` seed-7 file exists but the newest is used.

**Statistics:** CIs are Student-t, with exact sign-flip p at n<=16 (corrected after review; see `lib/stats.py`).

_Superseded text:_ most runs are from harness hash `63196db22b74`; one older `l0` seed-7 file exists but the newest is used.
The harness was being edited by another session during the work, so re-run if the code has moved on.

## 1. The measurements can be trusted (X0)
- Books balance exactly (offtake = units x ASP, units = organic + ad; error 0 in all runs).
- The offline oracle reproduces served impressions **exactly** on clean auctions (max error 0 across 12 seed/day samples).
- A/A difference is exactly 0, so any non-zero paired difference is a real policy effect, not noise in the harness.
- Method note: budget exhaustion is *not local*. When one campaign runs out, the market re-shares impressions among its siblings
  in later dayparts. Only 22-72% of auction rows are "clean"; 6-15% of potential impressions are lost to run-out.

## 2. The headline lift is small and not yet statistically resolved
CIs are Student-t (the earlier percentile bootstrap was too narrow at n=6; corrected after review).
| Comparison | Mean lift | 95% CI (t) |
|---|---|---|
| L0 vs baseline | +0.23% | 0.07 .. 0.40 (p~0.015) |
| L0 vs no-op | +0.07% | -0.05 .. 0.19 (includes zero) |
| baseline vs no-op | -0.17% | -0.36 .. +0.03 (**not shown** to be worse than no-op) |

- On 20 fresh worlds (seeds 303-322) L0 vs no-op is **+0.13% (CI 0.03..0.23)**: a small real gain. Baseline is -0.23% vs no-op there.
- Each comparison has its own spread, so its own MDE (reported per row in the X2 tables); the earlier "0.13-0.21pp" was from L0-vs-baseline only.
- Lift is back-loaded: week 6 gives +0.85% vs baseline; weeks 1-3 are about 0. A 42-day window under-states steady state.

## 3. Where the lift comes from, and why direct ROAS misleads (X0.4)
- L0's gain over no-op is ad value **+60.9k** offset by organic value **-49.1k**: most ad revenue is cannibalised organic.
- Brand keywords: direct ROAS 16-17 but true iROAS ~1.9; only ~11% of brand ad orders are incremental. Generic: incrementality 0.53.
  Competition: 0.85 (genuinely incremental but low direct ROAS 1.3).
- Implication: the floor metric (direct ROAS) rewards exactly the keywords that add the least real value.

## 4. Which L0 components earn their keep (X2)
Two data sets: dev6 = seeds 7/11/23/42/101/202 (used in earlier findings, so 101/202 are no longer held out);
fresh20 = seeds 303-322, never used before. Seeds 1001-1010 are reserved untouched for a final check.

| Arm | dev6 vs L0 (t CI) | fresh20 vs L0 (t CI) | Floor met (dev6 / fresh20) | Reading |
|---|---|---|---|---|
| no headroom gate | +0.85 (0.61..1.08) 6/6 seeds | **+0.86 (0.74..0.99) 20/20** | 6/6, 20/20 | **Replicates.** Gate costs ~0.86pp; spend +9.4%; min floor margin 0.09 vs L0 0.20 |
| no cuts | +0.13 (0.01..0.25) | **+0.05 (-0.03..0.13), 8 worse/12 better** | 6/6, **18/20** | **Does not replicate.** Cuts are not net-negative; they are floor insurance |
| no gate AND no cuts | +1.10 (0.80..1.40) | +1.06 (0.94..1.19) | 6/6, **11/20** | Biggest offtake, but breaks the floor in 9/20 worlds: the score would be void |
| cuts only | -0.37 (-0.43..-0.31) | not run | 6/6 | Worse than no-op in dev |
| no budget raises | -0.20 (-0.30..-0.10) 6/6 worse | not run | 6/6 | Budget raises earn their keep |
| no precheck / reprice / sibling holds | -0.04 / -0.04 / 0.00 | not run | 6/6 | Within noise (precheck p=0.06) |

Takeaways (revised after review and the fresh-seed run):
- **The headroom gate is the one robust drag.** Removing it alone keeps the floor in 26/26 *fresh/dev* worlds and gains ~0.86pp, but missed the floor in 1 of 10 later unseen worlds (§8), so its safety is not guaranteed.
- **Cuts are what buy floor margin.** Removing them drops the min margin to 0.05 (dev) / -0.05 (fresh) and breaks the floor in 2/20
  fresh worlds. The dev6 "cuts cost money" reading was a small-sample artefact; do not remove cuts. The gate and cuts effects are
  not additive: removing both gives +1.06 but fails the floor in 45% of worlds.
- **Do-nothing is itself unsafe**: no-op misses the floor in 3/20 fresh worlds, and L0 leaves ~0.2 ROAS above the floor unused
  (L0 spends ~5% less than no-op), i.e. offtake left on the table that the gate is holding back.
- The earlier note that only the gate and cuts effects clear the MDE was wrong: no-budget (-0.20, 6/6 worse) and cuts-only (-0.37)
  are equally resolved. Sign-flip p at n=6 can be no smaller than 0.031.

## 5. What the shipped actions really do (X3.3, 321 actions, within-week paired removal)
| Action | n | True Δspend / projected | True offtake per rupee |
|---|---|---|---|
| Budget raise | 32 | 3.95x | 1.76 |
| CPM raise (reprice) | 39 | 1.47x | 3.14 |
| CPM cut (base) | 250 | 2.18x | **0.75** |

- Cuts are 78% of all actions and the least efficient: cutting ~₹96k spend lost ~₹72k offtake.
- Spend projections are too low everywhere; budget-raise revenue is under-projected 2.96x. Per-action revenue correlation with
  truth is weak (0.02 reprice, 0.24 cut, 0.40 budget).
- Sizing rank: projected marginal ratio vs true marginal offtake per rupee, Spearman 0.41 (n=70): informative, noisy.

## 6. Revised story
**Raises (budget, reprice) create the value, the headroom gate throttles it (robust, replicated on 20 fresh worlds), and cuts are
the floor insurance that lets raises be safe.** X3.3 shows cuts are inefficient per rupee (0.75 offtake/rupee) *within their week*,
but X2 shows removing them does not raise offtake on fresh worlds and costs floor safety. The unused ROAS margin is the opportunity:
relax the gate while keeping cuts. Tested in §8: relaxing the gate's *minimum allowance* while keeping cuts recovers most of the gain (+0.8pp), but a fixed minimum missed the floor in 1 of 10 unseen worlds, so the relaxation must be state-dependent. That was built and confirmed on untouched worlds (§8b).

## 7. Limitations (read with §8-§11)
- Dev-structure worlds plus 13 self-authored perturbed worlds (X7.3, §14, 3 seeds each); the private eval scenario's actual values and shocks are untested.
  The fresh20 set confirms generalisation across random draws only.
- The floor is evaluated per run against the warm-up ROAS; eval scenarios with shocks may cut margins further.
- p-values at n=20 are not given (exact sign-flip enumeration is limited to n<=16); t-CIs are used.
- X3.3 counts only within-week effects; carry-over (e.g. cuts lowering later ladder state) is excluded, which may flatter or
  hurt cuts.
- No LLM layer has been measured at all (X4/X5 not started).
- Floor margin was checked only at the realised ROAS, not under a tighter tolerance.

## 8. Gate sweep with cuts kept (item 1, 2026-10-03)
Full detail in `../logs/2026-10-03-experiments-log.md`; tables in `results/x2_ablation_gate_sweep.md` and `x2_ablation_reserved10.md`.
- **The cost of the gate is almost entirely its minimum allowance.** Scaling the run fractions barely helps (x3 = +0.16pp); raising the
  minimum allowance from 300 to 1000 / 2000 / 3000 / 5000 ₹/day gives +0.41 / +0.70 / +0.80 / +0.86pp on 20 fresh worlds (no gate = +0.86),
  floor met 20/20 in each, min ROAS margin falling from 0.20 to 0.15 / 0.12 / 0.09.
- **Reserved-seed confirmation (1001-1010, once, rule fixed in advance: highest lift with floor 20/20 and margin >= 0.10 -> min 3000):**
  +0.76pp (CI 0.56..0.96, p=0.002, better in 10/10) **but the ROAS floor was missed in 1 of 10 worlds** (seed 1002, margin -0.015;
  seed 1008 +0.017), and no-gate does the same. L0 meets the floor 10/10.
- **So:** the lift is real and replicates; the safety does not fully. A fixed minimum allowance spends the same ₹ whether or not
  margin exists, and the G8 guardrail did not catch it, consistent with X3.3 (projected spend is 1.5-4x too low). Do not recommend
  `min_allowance=3000` as-is. Fix: make the minimum state-dependent (done and confirmed, §8b); `min_allowance=2000` kept 0.148 margin
  on fresh20 but is untested on unseen worlds.
- Caveat: 1/10 is a small sample; the true miss rate could be anywhere from ~0.3% to ~45% (exact 95% interval). Reserved seeds are now spent.

### 8b. State-dependent minimum allowance (1b) and its confirmation
`StateMin` (`experiments/lib/switchable_policy.py`): run 1 gets a fixed `run1_min`; from run 2 the minimum is `min(3000, cap_frac x banked headroom)`, so a
thin-margin world gets little extra spend and a roomy one gets up to 3000. Tables: `results/x2_ablation_state_min.md`, `x2_ablation_confirm2001.md`.
| Set (worlds) | `sm_r1500_c1.0` vs L0 | Floor met | Min margin (L0) | Fixed 2000 / 3000 vs L0 | Floor met (2000 / 3000) |
|---|---|---|---|---|---|
| fresh20 (303-322; tuned here) | +0.53 (0.45..0.61), 20/20 better | 20/20 | 0.19 (0.20) | +0.70 / +0.80 | 20/20 / 20/20 |
| 1001-1010 (spent; diagnostic) | +0.42 (0.31..0.53) | 10/10 | 0.119 (0.140) | +0.70 / +0.76 | 10/10 / **9/10** |
| **2001-2010 (untouched; pre-registered, run once)** | **+0.32 (0.23..0.41), 10/10 better, p=0.002** | **10/10** | 0.287 (0.304) | +0.38 / +0.45 | 10/10 / 10/10 |
- **Pre-registered rule: recommend `sm_r1500_c1.0` only if the floor is met 10/10 and the lift CI is above 0. It passed.**
- The lift shrinks as worlds get roomier (+0.53 -> +0.42 -> +0.32); it never costs margin. The fixed minimums gain more but spend margin
  (2000 on thin world 1002: margin 0.047; 3000: a floor miss there). Over all unseen sets, fixed 3000 has 1 floor miss in 20 worlds.
- Caveat: 2001-2010 contained no thin-margin world (L0 min margin 0.30), so it confirms lift and compliance but does not stress the floor; the stress evidence is
  seed 1002. Other arms were also explored by a parallel session, including on seeds 2001-2010 after results were visible, so only the pre-registered arm should be quoted as confirmed; any further confirmation needs a new reserved seed set (e.g. 3001-3010).

## 9. Each module against truth (X1; dev worlds, 6 seeds; `results/x1_modules.md`)
- **Spend forecast:** the grid's live-bid forecast over-predicts the realised week about **1.7x** (real/pred spend 0.60, revenue 0.51) on campaigns with an untouched bid
  and no run-out, and ~1.65x vs the trailing 28 days. Documented as "unconstrained", but not only a budget effect. Mechanism supported by X3.1 (§13): the grid predicts a step function where real spend is smooth in bid; not fully isolated.
  Levels are over-forecast while marginal moves are under-forecast (X3.3 section 5): the grid is wrong in both directions at once.
- **Incrementality (iota):** within-type correlation with truth ~0 (brand 0.02, competition 0.03, generic -0.07); biased high for brand (+0.12) and generic (+0.14);
  no improvement from run 1 to 6.
- **Sibling leader:** truly best in 70% of clear markets, 56% of near-ties (value ratio 0.92 / 0.88).
- **Headroom:** allowance 300 -> 966 INR/day (all of it in run 6) while banked headroom reaches 6.6k; **46-105k INR of unused slack per world** at the end.
- **Precheck:** 442 proposed = 442 shipped (guardrails block nothing after it); 130 dropped by precheck. The false-negative side is unmeasured.
- **Shocks:** OSA drop recall 1.00 / precision 1.00; price recall 0.43 / precision 0.08; demand (+15%) recall 0.12. First detection 7 days after onset (a 14 days once).
- **Floor view of actions (X3.3):** cuts remove spend at marginal dROAS 1.25 (floor ~4.34) and so *raise* portfolio ROAS; budget raises add spend at 4.04 (dilute);
  CPM raises 4.35 (neutral). Cuts pay for the raises.

## 10. Can an LLM leaf matter? (X5.1 / X5.2; scripted leaves, $0; `results/x5_llm_aided.md`)
Depth L2, 6 dev worlds, paired vs L0. `oracle` answers from hidden truth (an upper bound built from proxies, e.g. value per impression x 1000 / CPM > 1).
| Leaf (params) | Answered calls / world | Best passive/active/random vs L0 | Oracle vs L0 |
|---|---|---|---|
| L1 bid size (default) | ~2 | 0.000 | 0.000 |
| L2 shock (default) | ~6 | 0.000 | -0.000 |
| L3 sibling (default) | ~30 | +0.021 random (CI -0.012..0.054) | -0.002 |
| L6 review (default / recal) | ~1 / ~3 | always-veto -0.056 / -0.140 | -0.030 / -0.061 |
| L4 explore (recal) | ~30 | random -0.100, always-yes -0.070 | -0.033 (CI -0.184..0.117) |
| all leaves (default / recal) | | always-yes -0.063 / -0.235 | -0.050 / -0.123 |
- **No leaf improves offtake significantly, not even with answers from hidden truth.** Leaves that act (veto, explore) lower it; leaves that rarely fire (L1, L2, L6) cannot matter.
- Floor met 6/6 and zero fallbacks in every arm. Triggers: L3 and L4 about 5 per run, L1 / L2 / L6 about 0.3 / 1 / 0.2 per run.
- **Implication:** the paid slice is not worth running as configured; effort belongs on trigger design and what the leaves are asked to decide.
- Caveat: oracle answers are proxies, not the best possible answers; 6 worlds; one scripted decision rule per leaf.

## 11. Open items
Done since this section was first written: X7.3 (§14), X3.1 (§13), W0 (§12). Open: a new untouched confirmation set (3001-3010), the cut-reordering test (competition and brand first), the oracle-iota test, the LLM trigger redesign, and the private eval scenario. See `PRESENTATION_TALLY.md` and `recommendations/`.

## 12. W0: why the old harness measured +0.82% and today's +0.23% (`results/w0_old_vs_new_harness.md`)
Old harness (commit `0b73557`) simulated from a separate git worktree; `gpc/` is identical in both commits, and the old worktree's baseline equals
today's exactly (asserted), so the comparison is paired and valid. 6 dev worlds.
| Comparison | Mean | t-CI | Worlds |
|---|---|---|---|
| old L0 vs baseline | **+0.824%** | 0.55..1.10 | 6/6 better |
| new L0 vs baseline | +0.234% | 0.07..0.40 | 6/6 better |
| no-gate vs baseline | +1.082% | 0.77..1.39 | 6/6 better |
| **old L0 vs new L0** | **+0.589pp** | 0.40..0.78 | 6/6 |
| old L0 vs no-gate | -0.255pp | -0.36..-0.15 | 6/6 |
- **The old +0.82% is reproduced exactly**, including the held-out seeds (101 +0.936%, 202 +1.116% vs the paper's +0.94 / +1.12). The earlier
  report measured correctly; the code changed.
- **The 483ea9e correctness fixes cost 0.59pp of offtake.** The old sizing overshot its allowance (17-33x per the critique) and spent 7% more; the
  fix made it respect an allowance that is too tight (§9: 46-105k INR unused slack). Old L0 met the floor 6/6 on dev (min margin 0.227 vs 0.244).
- **So the fix was right and the allowance is the problem.** The confirmed state-dependent minimum (§8b/§8c, +0.32..+0.53pp, floor-safe on thin
  world 1002) recovers most of the old lift while keeping sizing correct. Whether the old overshoot would have missed the floor on thin worlds is untested.

## 8c. State-dependent minimum allowance (1b) — full table, 2026-10-03 (detail for §8b)
Rule (`lib/switchable_policy.py::StateMin`): harness minimum zeroed; run 1 gets a fixed `run1_min`; from run 2 the minimum is
`min(3000, cap_frac x banked headroom)`. So spend extra only where margin has actually been banked.
Tables: `results/x2_ablation_state_min.md` (tuning, fresh20), `x2_ablation_diag1000.md` (spent seeds, diagnostic), `x2_ablation_confirm2000.md` (confirmation).

| Arm | fresh20 lift (tuning) | min margin | 1001-1010 lift / floor / min margin (diagnostic) | **2001-2010 lift / floor / min margin (confirmation, run once)** |
|---|---|---|---|---|
| L0 | 0 | 0.20 | 0 / 10 / 0.140 | 0 / 10 / 0.304 |
| **sm_r1500_c1.0** (pre-registered primary) | +0.53 | 0.19 | +0.42 / **10/10** / 0.119 | **+0.32 (0.23..0.41), 10/10 better, floor 10/10, 0.287** |
| gate_min2000 (fixed) | +0.70 | 0.15 | +0.70 / 10/10 / 0.047 | +0.38 (0.29..0.48), floor 10/10, 0.286 |
| sm_r3000_c4.0 (second candidate) | +0.75 | 0.14 | +0.62 / 10/10 / 0.057 | +0.43 (0.32..0.55), floor 10/10, 0.282 |
| gate_min3000 (fixed) | +0.80 | 0.12 | +0.76 / **9/10** / -0.015 | +0.45 (0.32..0.57), floor 10/10, 0.282 |
| no-op | -0.13 | -0.07 | -0.08 / 7/10 / -0.079 | -0.12 / **9/10** / -0.027 |

Reading:
- **Pre-registered test passed:** `sm_r1500_c1.0` met the floor 10/10 on untouched seeds and its lift CI is above 0. Across the 20 unseen
  worlds (1001-1010 + 2001-2010) it met the floor 20/20 with min margin **0.119**.
- **The state-dependent rule buys safety, not lift.** On the thin-margin worlds it keeps a 0.12 margin where a fixed 2000 leaves 0.05 and a
  fixed 3000 misses (-0.015). Lift is lower: +0.3 to +0.4pp, about 40-55% of the no-gate gain.
- **Lifts on 2001-2010 are smaller for every arm** (fixed 3000: +0.45 here vs +0.80 on fresh20 and +0.76 on 1001-1010); worlds differ in how much
  banked headroom the gate was withholding. The ranking of arms is stable; the size of the gain is world-dependent (plan for +0.3 to +0.8pp).
- **Caveat on the confirmation:** 2001-2010 contained no thin-margin world (L0's lowest margin there is 0.30), so its 10/10 says little about
  safety. The thin worlds are in the 1001-1010 diagnostic (1002, 1008), where `sm_r1500_c1.0` kept 0.119 and the fixed arms did not.
- The fixed 3000's floor miss did not recur on 2001-2010 (10/10), so its true miss rate is about 1 in 20 unseen worlds, not zero and not
  well pinned. Two candidates shared one confirmation set; both passed, and neither pass is a surprise given the outcomes on the spent seeds.
- **Recommendation to the owner of `harness/`:** make the minimum allowance state-dependent (run-1 ~1500 INR/day, then
  `min(3000, 1.0 x banked headroom)`), not a larger fixed number. Expected +0.3 to +0.5pp at L0's floor margin. A fixed 2000 is the
  higher-lift/lower-margin alternative. Not applied here: `harness/` is not ours to edit.
- Caveats: dev-scenario worlds only at the time of this section (X7.3 later covered 13 perturbed worlds, §14); the tuning grid was run twice on fresh20, so only the 2001-2010
  and 1001-1010 numbers are unbiased; the harness's G8 guardrail still does not catch over-spend (X3.3: projections 1.5-4x low), so the cap
  on banked headroom is doing the safety work G8 should.

## 13. Exploratory: skipping generic cuts (fresh20; `results/x2_ablation_no_generic_cuts.md`)
X3.3 by keyword type showed generic cuts lose 0.90 offtake per INR (competition 0.36), so an arm that skips generic cuts was tried. **Not supported:** +0.09pp (CI 0.01..0.17, 13 better / 7 worse),
floor met 19/20 (min margin -0.003), mean margin 0.181 vs L0 0.394 (no cuts at all: 0.076). Generic cuts carry most of the floor insurance. A reordering (competition and brand first) is untested.
Also X3.1 (bid dose-response, 2 seeds): the grid forecasts a step function where real spend is smooth and monotone in bid; the 1.7x over-forecast replicates (real/pred 0.42-0.65 at the live bid, 0.88-0.94 at +50%).

## 14. Generalisation to perturbed worlds (X7.3; 13 worlds x 3 seeds = 39 pairs; `results/x7_generalisation.md`)
Worlds: 7 value variants (incrementality +-30%, auction sigma 0.2/0.45, appeal rotated, intent x1.25/x0.8) and harness_eval's 6 shock-schedule worlds P1-P6, seeds 303-305.
Lift vs full L0 on the same world+seed (t-CI over pairs; pairs within a scenario share parameters, so CIs are optimistic):
| Arm | Value worlds (21) | Shock worlds (18) | Floor met (value / shock) | Min margin (value / shock) |
|---|---|---|---|---|
| L0 | 0 | 0 | 21/21, 18/18 | 0.113 / 0.065 |
| **`sm_r1500_c1.0`** | **+0.51 (0.41..0.61), 21/21 better** | **+0.57 (0.46..0.69), 18/18 better** | **21/21, 18/18** | 0.089 / 0.060 |
| fixed min 3000 | +0.76, 21/21 better | +0.79, 18/18 better | 20/21, 18/18 | -0.019 / 0.012 |
| no gate | +0.79, 21/21 better | +0.80, 18/18 better | 20/21, 18/18 | -0.038 / 0.009 |
| no cuts | -0.03 (-0.13..0.07) | -0.02 (-0.14..0.10) | 21/21, **12/18** | 0.007 / **-0.277** |
| no-op | -0.12 | -0.10 | 19/21, **11/18** | -0.013 / -0.312 |
- **The gate result generalises:** removing or relaxing the gate gains 0.4-1.1pp in every one of the 13 worlds (smallest where intent is low or auction spread high: V_intent_lo +0.32, V_sigma_hi +0.33 for `sm`).
- **`sm_r1500_c1.0` held the floor in all 39 pairs**, including the hardest shock worlds where L0's own minimum margin is only 0.065 (`sm`: 0.060). Fixed 3000 and no-gate each missed the floor once (V_intent_hi); both are unsafe by the same mechanism seen on seed 1002.
- **Cuts matter more in shock worlds:** removing cuts breaks the floor in 6 of 18 shock pairs (P2 and P4: 3 each; min margin -0.277); doing nothing breaks it in 7 of 18. "Keep the cuts" is confirmed beyond dev.
- L0 vs no-op is small but consistent: +0.10 (shock), +0.12 (value).
- Caveats: 3 seeds per world; self-authored perturbations (not the private eval scenario); `sm_r1500_c1.0` was chosen on dev-structure worlds and then evaluated here without retuning, which is the intended test.

## 15. X3.1 bid dose-response: why the grid mis-forecasts (12 cells x 7 bid steps, seeds 7 and 11; `results/x3_1_bid_dose_seed{7,11}_run3.md`)
- **Mechanism identified.** For every raise step (+10/+30/+50%) the grid predicts exactly the same spend and revenue as at the live bid (e.g. brand, seed 7:
  9,127 INR at steps 0/+10/+30/+50). `grid.slot_at_bid` picks the best slot whose *median* clearing price the bid meets, so at the live bid the grid already
  assumes slot 1 is won outright. The market sells a share: the true slot-1 share at the live bid is **0.42-0.83** (by keyword type and seed) and reaches
  ~1.0 only at +30-50%, which is where real spend finally meets the grid's number.
- One assumption explains two module findings: the **~1.7x level over-forecast** (X1.1: full share assumed today) and the **1.5-4x marginal under-forecast**
  (X3.3: a raise that buys the missing share is predicted to change nothing).
- **Competition-keyword raises lower total offtake** in both seeds (-0.03 to -0.25 offtake per INR) while their ad revenue rises. Hypothesis, untested: the
  extra spend exhausts the campaign budget earlier and starves its better keywords. Generic raises have diminishing returns (seed 7: 0.58 -> 0.35 per INR
  from +10% to +50%; seed 11 turns negative at +50%). Brand is noisy across seeds.
- Recommendation for the harness owner: price raises along the share curve (a policy can estimate the competitor-bid spread from its own slot mix) instead of
  the median-price step; hold competition raises on budget-bound campaigns until the starvation hypothesis is tested.
- Limits: 2 seeds, one run state (run 3), one week, 12 cells (4 per type) summed by type.
