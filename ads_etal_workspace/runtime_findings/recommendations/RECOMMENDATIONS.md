# Recommendations from the measurement experiments

> **As of 2026-10-03, evening.** Every recommendation here comes from a measured result in `runtime_findings/FINDINGS.md`,
> `logs/2026-10-03-experiments-log.md` or `experiments/results/`, on harness commit `483ea9e` (code hash `63196db22b74`), at $0.
> `harness/`, `gpc/` and `harness_eval/` are owned by another session and were **not** edited. Recommendations that touch them are
> addressed to that session.
>
> **Companion files in this folder** (added later, same evidence, shorter and grouped by audience): `README.md` (priority table), `01-harness-changes.md`,
> `02-llm-layer.md`, `03-next-experiments.md`, `04-measurement-practice.md`. This file is the detailed source; where they differ, this file's
> evidence sections and the dated updates win.
>
> **Status key:** **confirmed** = replicated on worlds not used to choose it. **supported** = measured, not yet replicated or confirmed.
> **pending** = depends on an experiment that is running now (named). **hypothesis** = reasoned from results, untested.

## Summary table

| # | Recommendation | For | Priority | Status | Expected effect |
|---|---|---|---|---|---|
| R1 | Relax the headroom gate through a **state-dependent minimum allowance**; do **not** use a fixed 3000 INR/day minimum | harness | P0 | **confirmed** (2001-2010: +0.32pp, floor 10/10; see R1) | +0.3 to +0.5pp offtake at L0's floor margin |
| R2 | **Keep cuts**; if anything, order them by lowest marginal ROAS first | harness | P0 | confirmed (keep) / hypothesis (ordering) | avoids 2/20-9/20 floor misses |
| R3 | Treat the 2026-10-03 sizing fix as a **deliberate trade-off**, not a free fix: it cost ~0.6pp | harness, docs | P0 | confirmed (W0) | correct reading of +0.82% -> +0.23% |
| R4 | **Correct the spend projections** used by the guardrails and the gate (level over-forecast ~1.7x; marginal under-projection 1.5-4x) | harness | P1 | supported; mechanism supported by X3.1 (share vs certainty) | fewer floor surprises when the gate is relaxed |
| R5 | **Don't run the paid LLM slice as configured**; redesign triggers and what the leaves decide first | harness, plan | P1 | supported (X5.1, 6 worlds) | saves spend that cannot move offtake today |
| R6 | **Remove or restrict the L6 veto** (and keep L4 explore off) | harness | P1 | supported (X5.1) | +0.03..0.14pp vs vetoing; no downside seen |
| R7 | **Fix the ι estimator only if it changes decisions**: run the oracle-ι test first, then add OSA and search-prior controls | experiments, then harness | P2 | hypothesis | unknown; measured accuracy is ~0 within type |
| R8 | **Shock detector**: control false positives on price shocks; aggregate keyword-wide for demand shocks | harness | P2 | supported (X1.6) | precision 0.08 -> ? ; recall 0.12 -> ? |
| R9 | **Deprioritise sibling-leader fixes** | harness | P3 | supported (X1.3 + X5.1) | none expected (oracle leader choice adds 0) |
| R10 | **Measurement standards**: t-CIs, lift vs no-op, floor margin in every table, fresh seeds, code hash | harness_eval, reports | P1 | confirmed (applied in experiments) | prevents the overstated readings we hit |
| R11 | **Update stale documents** (paper rev 5, deep dive rev 3, critique status, runtime report) | docs | P1 | confirmed | numbers match the current code |
| R12 | **Next experiments**: offtake-vs-margin frontier, oracle-ι, generalisation | experiments | P1 | planned | decides R1/R4/R7 settings |

---

## R1. Relax the gate with a state-dependent minimum allowance (P0, confirmed)

**Evidence**
- Removing the gate adds **+0.86pp** vs L0 (20/20 fresh worlds, floor met 20/20). The gate is the single robust drag (X2).
- Most of its cost is the small fixed minimum allowance in early runs, where nothing has been banked yet. Fixed minimum 1000 / 2000 / 3000 /
  5000 INR/day gains +0.41 / +0.70 / +0.80 / +0.86pp on fresh20, with min ROAS margin falling 0.21 -> 0.09.
- **A fixed 3000 missed the floor in 1 of 10 unseen worlds** (seed 1002, margin -0.015). A missed floor voids the score.
- **State-dependent minimum** (run 1: fixed amount; later runs: at most a fraction of banked headroom): best setting `run1_min=1500,
  cap_frac=1.0, min_amt=3000` gives **+0.53pp** (0.45..0.61) on fresh20 with min margin 0.193 (L0: 0.201).

**Recommendation (to the harness session):** replace `headroom_min_allowance_inr_day` with a rule of this shape:

```
allowance = max(schedule_slice_of_banked_headroom, 300,
                run1_min                           if run == 1
                min(min_amt, cap_frac x banked_headroom_inr_day)   otherwise)
```

The run-1 amount is the strongest single lever (run1 1500 vs 300 roughly doubles the gain).

**Confirmed (updated 2026-10-03 by the second session):** pre-registered run on untouched seeds 2001-2010 (run once): `sm_r1500_c1.0` **+0.32pp**
(0.23..0.41, better in 10/10), floor met 10/10, min margin 0.287 (L0 0.304). Over the 20 unseen worlds (1001-1010 + 2001-2010) it met the floor 20/20
(lowest margin 0.119); fixed 3000 met it 19/20; fixed 2000 20/20 but with margin down to 0.047. Caveat: 2001-2010 held no thin-margin world, so the
safety evidence is seeds 1002/1008. Expect +0.3 to +0.5pp, not the +0.53 tuning number. **Do not adopt a fixed 3000.**

**Limitation:** tuned on dev-scenario worlds. **Update (X7.3 done, 2026-10-03):** on 13 perturbed worlds x 3 seeds (7 value variants, P1-P6 shock worlds) `sm_r1500_c1.0` gained +0.51pp (value) / +0.57pp (shock), better in 39/39, and met the floor in 39/39, including shock worlds where L0's own minimum margin is 0.065 (sm: 0.060). Fixed 3000 and no-gate missed the floor once each (V_intent_hi). Self-authored perturbations, 3 seeds per world: the eval scenario itself is still untested.

## R2. Keep cuts (P0, confirmed); order them by marginal ROAS (hypothesis)

**Evidence**
- Removing cuts: +0.13pp on dev6 but **+0.05pp (CI spans 0) on fresh20**, with the floor missed in **2/20** worlds. Removing gate and cuts together:
  +1.06pp but the floor missed in **9/20**.
- Cuts remove spend at a marginal direct ROAS of **1.25** against a floor of ~4.34 (X3.3 floor view). They raise portfolio ROAS, and that
  is what makes raises affordable.
- Per rupee within their week, cuts are the least efficient action (0.75 offtake per INR vs 1.76-3.14 for raises).

**Recommendation:** keep the ladder-paced cuts. Untested refinement: rank cut candidates by marginal ROAS so the lowest-ROAS spend goes first.
That maximises floor margin bought per rupee of offtake lost.

**Update (2026-10-03):** the obvious test of this idea, an arm that skips generic cuts (`no_generic_cuts`, fresh20), did **not** support it: +0.09pp (CI 0.01..0.17) but floor met only 19/20 and mean margin 0.181 vs 0.394 for L0 (no cuts at all: 0.076). Most cut spend is generic, so generic cuts are most of the insurance. Skipping them is not viable; only a reordering (competition/brand first, generic as the fallback) is still untested.

## R3. Read the sizing fix as a trade-off (P0, confirmed)

**Evidence (W0):** the pre-fix harness (`0b73557`) reproduces **+0.824%** vs baseline exactly; the current harness gives +0.234%. Old minus new:
**+0.59pp** (0.40..0.78, 6/6 seeds), with 7% more spend and the floor met 6/6. The fix made the allowance binding (runtime report F1).

**Recommendation:** in the harness docs and reports, state that the F1 fix cost ~0.6pp of offtake for floor safety, and choose the gate setting
from the measured trade-off (R1, R12 frontier) rather than treating either extreme as correct.

**Thin-world diagnostic (done, seeds 1001-1010, already spent so diagnostic only):** the old harness gains **+0.44pp** over today's L0 (0.31..0.57) and
meets the floor 10/10, but with margins of only **0.050 and 0.057** in the two thin worlds (1002, 1008; today's L0: 0.140 / 0.234). On the same worlds
the R1 arm (`sm_r1500_c1.0`) gains **+0.42pp** with margins **0.119 / 0.195**. So the fix did buy real margin where margin is thin, and **R1 recovers about the
old harness's lift while keeping 2-3x its margin in those worlds**: a better point on the trade-off than either the pre-fix behaviour or a fixed minimum.

## R4. Correct the spend projections (P1, supported)

**Evidence**
- The grid's live-bid spend forecast is **~1.7x too high** vs the realised week, even for untouched campaigns that never ran out of budget
  (real/pred 0.60 spend, 0.51 revenue; X1.1). It is also 1.65x the trailing 28-day realised spend.
- Marginal moves go the other way: true Δspend is **1.5-4x the projection** (budget raises 3.95x, CPM raises 1.47x, cuts 2.18x; X3.3).
- The guardrail did not prevent the seed-1002 floor miss, consistent with an optimistic projection.

**Recommendation:** calibrate projections against realised data before relying on them for safety, e.g. per-cell realised/predicted ratios
from the last 2-4 weeks, and a spend-under-projection factor in the floor check.

**Update (X3.1 reported, 2026-10-03):** bid dose-response on 2 seeds x 12 cells replicates the gap (real/pred spend 0.42-0.65 at the live bid, 0.88-0.94 at +50%). Real spend is smooth and monotone in bid (12/12 cells) while the grid predicts a step function (about 3 distinct values across 7 bid steps; it predicts 0 at -30% where real spend is 6.8-7.9k INR). So the mechanism is **supported**: the grid assumes the affordable slot with certainty where the market gives slot shares. Not isolated: slot-1 share explains the gap well in seed 7 (corr 0.89) and only partly in seed 11 (0.44). Suggested fix direction: model slot shares, or calibrate the forecast per cell from realised/predicted history.

**Mechanism (X3.1, done, seeds 7 and 11):** at the live bid the grid predicts 1.6-2.4x the realised spend, and the gap closes as the bid rises
(+50%: real/pred 0.68-1.14). That fits the grid assuming the best affordable slot is won with certainty, where the market gives a share of auctions
that only approaches 1 at high bids. A structural fix is to predict with the auction-share model (`_slot_shares`-style, with an estimated spread)
instead of a step function, or to calibrate per cell as above. X3.1 also shows returns fall fast past a +10-30% raise, and competition-keyword raises
returned ~0 or negative offtake per rupee in both seeds, so **smaller raise steps** and **scrutiny of competition raises** are worth testing.

## R5. Don't run the paid LLM slice as configured (P1, supported)

**Evidence (X5.1, 6 worlds, scripted LLMs, 180 sims):** no leaf adds offtake in any mode, **including an oracle that answers from hidden truth**.
L1 fires ~2, L2 ~4-6 and L6 ~1-3 times per world, too rarely to matter. L3 fires ~30 times, but leader choice doesn't move offtake. Floor met
in every arm; 0 fallbacks.

**Recommendation:** hold the $3 paid slice. First change what the leaves are asked: the measured value is in *how much to spend and when*
(R1), not in tie-breaks or vetoes. A leaf deciding the run-1 allowance or the allowance cap fraction would sit on the lever that matters.
**Limitation:** oracle answers are proxies built from truth, not optimal answers.

## R6. Remove or restrict the L6 veto; keep L4 explore off (P1, supported)

**Evidence:** L6 always-veto **-0.056pp** (default params, p=0.031, worse in 6/6) and **-0.140pp** (recalibrated, p=0.031); even the oracle veto
-0.030 / -0.061. L4 explore -0.03..-0.10 (wide CIs). Vetoing removes raises, and raises are where the value is (R1, X3.3).

**Recommendation:** drop L6 at L2 depth, or let it only resize, never remove. Keep `explore.enabled=false`.

## R7. Fix ι only if it changes decisions (P2, hypothesis)

**Evidence (X1.2):** per-SKU ι estimates have ~0 within-type correlation with truth, biased high for brand (+0.12) and generic (+0.14), and they
don't improve with more data. Cause (constraints plan): cannibalisation explains ~9% of organic variance, and OSA and weekends move ads and
organic together. The deep dive's "bias worry not borne out" holds only for **pooled** type-level estimates.

**Recommendation:** run the oracle-ι arm first (L0 with true ι). If offtake doesn't move, ι accuracy is not worth engineering. If it does, add
OSA and search-prior controls, and a prior from public `organic_rank`. Bid dithering / IV comes only after that.

## R8. Shock detector (P2, supported)

**Evidence (X1.6, 6 worlds):** stock-out drops: recall 1.00, precision 1.00. Price shocks: recall 0.43, **precision 0.08** (208 flags elsewhere).
Demand shocks (+15%): **recall 0.12**. Detection is always 7 days after onset (the detector's window).

**Recommendation:** for price, require the CPM shift to appear across several cells of the same market before flagging (or apply a
multiple-testing control: ~100 z-tests per run). For demand, test keyword-wide aggregated reach rather than per cell. Since L2 shock raises
add nothing even with oracle answers (X5.1), this matters mainly for any future use of shocks, not for today's offtake.

## R9. Deprioritise sibling-leader fixes (P3, supported)

**Evidence:** the mechanical leader is truly best in 70% of clear markets and 56% of near-ties (X1.3), yet an oracle L3 leaf that picks the true best
leader adds **-0.002pp** (X5.1). Better leader choice does not move offtake in these worlds.

**Recommendation:** don't spend effort on leader accuracy (runtime report F5) until something shows it matters.

## R10. Measurement standards (P1, confirmed)

What went wrong before and is fixed in `experiments/`: percentile-bootstrap CIs too narrow at n=6, conclusions from dev seeds that didn't
replicate (cuts), "held-out" seeds that were used, lift reported without the floor, and a minimum detectable effect taken from the wrong comparison.

**Recommendation (for `harness_eval` and future reports):** Student-t CIs with exact sign-flip p; lift vs **no-op** as well as vs baseline (the
baseline is below no-op on fresh worlds, -0.23%); floor met and margin in every table; a fresh seed set for every confirmation, chosen and recorded
before running; results stamped with the code hash; perturbed worlds that change *values*, not only shock schedules.

## R11. Update stale documents (P1, confirmed)

| Document | What is stale | Correct now |
|---|---|---|
| `presentations/harness-vs-procllm-paper.md` (rev 5 header) | "+0.82%, 12 of 12 worlds" | +0.23% vs baseline on current code; +0.82% was `0b73557` (W0) |
| `presentations/harness-system-deep-dive.md` §6 ⑦⑧, §11.2, §11.5, §13 | μ-bisection sizing; run-1 allowance always 0; +0.82%/+0.66%; overshoot 17-33x | greedy knapsack within the allowance; 300 INR/day minimum; +0.23% / +0.07-0.13%; no overshoot (X1.4) |
| `presentations/harness-system-deep-dive.md` §6 ② | "ι bias worry not borne out" | holds for pooled estimates only; per-SKU estimates biased and uncorrelated (X1.2) |
| `presentations/harness-vs-procllm-critique.md` status | A1, A7 open | A1 and A7 fixed in `483ea9e` (verified); A4 upheld (L0 loses to baseline in 4/20 fresh worlds); A8 consistent with the seed-1002 miss |
| `runtime_feedback_improvement/RUNTIME_FEEDBACK_REPORT.md` | lift table, F1/F4/F6 open | F1, F4, F6 fixed; their cost measured (R3); F11 refined (early-run allowance is the binding lever) |

These edits are planned as part of the tally once the running experiments finish.

## R12. Next experiments (P1, planned)

From `runtime_constraints_workaround/PLAN.md` and `runtime_findings/NEXT_STEPS.md`:
1. **Offtake-vs-margin frontier** from existing arms (no new sims): the exchange rate between offtake and floor margin, and a principled replacement
   for the "margin >= 0.10" selection rule.
2. **Oracle-ι arm** (R7).
3. **X7.3 generalisation** (running) and **X3.1** (running) feed R1 and R4.
4. Only then: dithering/IV for ι, a share-aware arm, and a redesigned LLM leaf on the allowance (R5).

---

*To be updated when the 1b confirmation, X7.3, X3.1 and the thin-world W0 diagnostic finish. Statuses marked pending will change to confirmed or
withdrawn.*
