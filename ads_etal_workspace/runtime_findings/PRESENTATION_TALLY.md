# Presentations vs. measured results: tally

**Status: updated 2026-10-03 after X5.1 and the 1b confirmation finished. W0 added 2026-10-03 evening. All rows resolved; X7.3 and X3.1 done (18:35). No PENDING rows remain.**
Checks the quantitative claims in `presentations/` against the slice-and-dice experiments (`runtime_findings/FINDINGS.md`,
`experiments/results/`). Code under test: `grid-path-challenge` commit `483ea9e` (hash `63196db22b74`) unless stated.

Important context for every row: the three older documents (`harness-system-deep-dive.md`, `harness-vs-procllm-paper.md` (= v4),
`harness-vs-procllm-critique.md`, all 09:24) describe the harness **before** commit `483ea9e` (sizing rewrite, minimum allowance,
precheck before sizing). Where a claim was true of the old code and the code has since changed, the row says so rather than calling
it wrong. `measurement-experiments-snapshot.md` (16:27) was written from the same sources as this tally and is checked separately.

Verdicts: **holds** · **holds, changed since** (true of the old code, superseded by `483ea9e`) · **contradicted** · **partly** · **PENDING**.

**Decision (2026-10-03, user): the older decks (`harness-system-deep-dive.md`, `harness-vs-procllm-paper*.md`, `harness-vs-procllm-critique.md`) are left untouched until W0 settles the +0.82% vs +0.23% question. W0 has since reported (old harness reproduces +0.824%, today's +0.234%); the decks are still untouched, pending the user's choice of a correction note.** Recommendations are in `recommendations/`.

## A. Headline lift

| # | Claim | Where | Measured | Verdict |
|---|---|---|---|---|
| A1 | L0 beats baseline by **+0.82%** (CI +0.61..+0.99), 12/12 worlds | paper l.6, runtime report rev. 2 | W0: the old harness (0b73557) gives **+0.824%** (t-CI 0.55..1.10) under our paired measurement, 6/6 worlds. Current code (483ea9e): **+0.234%** (0.07..0.40); fresh20 +0.36% | **holds, changed since**: correct for the code it measured; the 483ea9e fixes cost **-0.59pp** (CI 0.40..0.78, 6/6 seeds) because sizing now respects a too-tight allowance |
| A2 | Lift +0.33% to +0.93% on four dev seeds | critique l.127, l.215 | W0 old code, seeds 7/11/23/42: +0.36 / +0.70 / +0.89 / +0.95% | **holds, changed since** (an earlier revision of the old code; same range) |
| A3 | Held-out seeds +0.94% / +1.12% | paper l.6 | W0 old code: 101 **+0.936%**, 202 **+1.116%** (exact match). Current code: +0.23 / +0.46% | **holds, changed since** |

## B. Sizing, headroom, gate

| # | Claim | Where | Measured | Verdict |
|---|---|---|---|---|
| B1 | Sizing overshoots the allowance 17-33x; acts as an on/off gate | critique A1, paper l.377 | Fixed in `483ea9e` (greedy ratio knapsack). Today the allowance binds: runs 1-5 average 300-966 INR/day allowance, 218-680 shipped (X1.4) | **holds, changed since**; the fix is what turned the gate into a real constraint |
| B2 | Late-run headroom goes unspent | paper l.403 | X1.4: banked headroom grows 0 -> 6.6K INR/day; end-of-window unused slack 46-105K INR per world (margin 0.24-0.54) | **holds**, and is now the largest measured opportunity (gate relaxation +0.53..+0.86pp) |
| B3 | G8 never trims anything (proposed = final) | critique l.71 | X1.5 on current code: 442 proposed = 442 shipped over dev6 | **holds** (still true after the fixes) |
| B4 | Headroom (cumulative, margined) and G8 (last 7 days, unmargined) constrain different windows | critique A8 | Not measured directly. Related: the fixed 3000 minimum missed the floor on seed 1002 although G8 never trimmed; X3.3 shows projected spend is 1.5-4x too low at the margin | **partly**: consistent with a guardrail that projects optimistically |

## C. Modules

| # | Claim | Where | Measured | Verdict |
|---|---|---|---|---|
| C1 | ι ordering right, errors both ways; "ι pushed toward 1" not borne out (pooled type-level, baseline data: brand 0.12, generic 0.50, competition 0.99) | deep-dive l.283-296 | X1.2, per-SKU estimates actually used by L0, on L0's own runs, 6 seeds: brand 0.24 vs true 0.12 (eff.), generic 0.68 vs 0.54, competition 0.82 vs 0.86; **within-type correlation with truth ~0** | **partly**: type ordering holds; the per-SKU estimates the policy uses are biased high for brand/generic and carry no within-type information. Different data and granularity from the deep-dive's check |
| C2 | leader_score = conv1 x ASP x ι picks the sibling to protect | deep-dive l.301 | X1.3: chosen leader is truly best in 70% of clear markets, 56% of near-ties (value ratio 0.92 / 0.88) | **partly**: better than chance, far from reliable |
| C3 | Precheck mirrors G0/G3/G4/G5/G7 (critique: overstated, G7 stricter) | critique A7 | X1.5: nothing precheck passes is blocked (0/442); 130 dropped; false-negative side not measured | **holds** for the direction measured |
| C4 | Shock detector flags reach / CPM / OSA shocks | deep-dive l.134, l.183 | X1.6: OSA recall 1.00 / precision 1.00; price recall 0.43 / precision 0.08; demand (+15%) recall 0.12; first detection 7 days after onset | **partly**: works for OSA only |
| C5 | Grid forecasts per-cell spend/revenue (used by projections and G8) | deep-dive l.270 | X1.1: live-bid spend over-forecast ~1.7x (real/pred 0.60 on untouched, not-run-out campaigns); X3.3: marginal Δspend under-forecast 1.5-4x | **contradicted as a forecast of levels** (documented as "unconstrained"); X3.1 (bid dose-response, 2 seeds) replicates the gap (real/pred 0.42-0.65 at the live bid, 0.88-0.94 at +50%) and shows the grid predicts a step function where real spend is smooth and monotone; mechanism **identified**: the grid's prediction is identical for every raise step and equal to its live-bid prediction (it assumes slot 1 won at the median price), while the true live-bid slot-1 share is 0.42-0.83 (FINDINGS §15) |

## D. LLM layer

| # | Claim | Where | Measured | Verdict |
|---|---|---|---|---|
| D1 | Each leaf is triggered by a mechanical condition, a handful of calls per run | paper l.91 | X5.2 final (6 dev worlds, depth L2, answered calls per **world** = 6 runs): defaults L3 30.3, L2 5.9, L1 1.8, L6 1.3, L4 0 (explore off); recalibrated adds L4 30.0, L2 3.8, L6 2.9 | **partly**: ~5 per run for L3 (and L4 when enabled), but L1, L2 and L6 fire about 0.3, 1 and 0.2 times per run, too rarely to matter |
| D2 | LLM depth never run with a real model inside a simulation | paper l.7 | still true; X5.1 is scripted ($0) | **holds** |
| D3 | Leaves can improve on L0 | (implied by the L1/L2 design) | X5.1 final, scripted leaves paired vs L0 over 6 dev worlds ($0): **no arm improves offtake significantly**. Best: L3 random +0.021% (CI -0.012..0.054). Oracle (hidden-truth answers): L1 0.000, L2 -0.000, L3 -0.002, L6 -0.030 (default) / -0.061 (recal), L4 -0.033. Always-veto L6 -0.056 (CI -0.111..-0.001). All leaves oracle -0.050 (default) / -0.123 (recal). Floor met 6/6 everywhere, 0 fallbacks | **contradicted for the configurations tested**: no evidence a leaf can add offtake at these trigger rates. Caveat: the oracle answers are proxies from hidden truth (value per impression x 1000 / CPM), not the best possible answers |
| D4 | Leaves are mis-calibrated at default parameters (explore disabled, review threshold) | runtime report F7 | X5.1: with the recalibration (explore on, review threshold 300) L4 and L6 fire more often (30 and 2.9 calls per world) but still lower offtake when they act (oracle -0.033, -0.061) | **partly**: recalibration raises the trigger rate, not the value |

## D'. Gate relaxation (post-dates the presentations)

| # | Claim | Where | Measured | Verdict |
|---|---|---|---|---|
| G1 | State-dependent minimum allowance (`sm_r1500_c1.0`) keeps L0's floor margin and adds offtake | snapshot §1, §5 | Pre-registered confirmation on untouched seeds 2001-2010 (run once): **+0.32%** (CI 0.23..0.41, better in 10/10), floor met **10/10**, min margin 0.287 (L0 0.304). Earlier: fresh20 +0.53%, floor 20/20; spent seeds 1001-1010 +0.42%, floor 10/10, thin world 1002 margin +0.119 | **holds**; lift shrinks from +0.53 to +0.32 as margins widen. Caveat: seeds 2001-2010 had no thin-margin world (L0 min margin 0.30), so the stress evidence is seed 1002 |
| G2 | Fixed minimum 3000 ruled out | snapshot §5, §12 | On 2001-2010: +0.45%, floor 10/10 (no thin world). Over all unseen sets (reserved + 2001-2010): 1 floor miss in 20 | **holds as a risk statement, not as a certainty**: the miss needs a thin-margin world |
| G4 | The gate and cuts findings hold beyond dev-structure worlds | snapshot §11 ("one scenario family") | X7.3, 13 perturbed worlds x 3 seeds: `sm_r1500_c1.0` +0.51 (value) / +0.57 (shock), better in 39/39, **floor met 39/39**; fixed 3000 and no-gate 38/39 (V_intent_hi); no cuts floor 12/18 in shock worlds (min margin -0.277) | **holds** (self-authored perturbations, 3 seeds each) |
| G3 | Fixed minimum 2000 is the aggressive alternative | snapshot §12 | 2001-2010: +0.38%, floor 10/10, margin 0.286; 1001-1010: +0.70%, floor 10/10, margin only 0.047 | **holds**: no miss yet, but a razor-thin margin on the thin world |

## E. Snapshot (`measurement-experiments-snapshot.md`)
Written from the same sources (last edit 18:10). Its numbers agree with this tally and FINDINGS; checked 2026-10-03 18:35. **Stale statements to update
(not edited here; `presentations/` changes need the user's go-ahead):**
| Line | Says | Now |
|---|---|---|
| 6 | ~200 simulations queued or running | nothing queued; all jobs done |
| 20, §8 title | X5.1 "interim" | final (§8 body already uses the final table) |
| 33-34, 63, 208 | W0 queued; hypothesis "the sizing fix enforced the gate" | **done**: +0.824% reproduced from `0b73557`; the `483ea9e` fixes cost -0.59pp (CI 0.40..0.78, 6/6). Hypothesis confirmed in direction; old L0 sits 0.26pp below no-gate, not equal to it |
| 256 | "traded about 0.6-0.9pp" | measured: **0.59pp** |
| 60, 210, 254 | X3.1 queued; grid fix "after X3.1 isolates the cause" | **done**: grid assumes slot 1 won at the median price, raise predictions flat, true live-bid slot-1 share 0.42-0.83; competition raises lower offtake (FINDINGS §15) |
| 238 | X7.3 "has not run yet" (Limitations) | done (rows 62 and 209 already say so); limitation now reads "self-authored perturbations, 3 seeds per world" |

No numeric disagreement found between the snapshot and the measured results; only status lines are out of date.
