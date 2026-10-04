# Proposed changes to `harness/` (not applied)

## H1. State-dependent minimum allowance (the gate fix)  — recommended
**Problem.** The headroom gate is the dominant drag on offtake. Removing it adds +0.86pp (20/20 fresh worlds). Almost all of that cost is the
fixed minimum allowance (300 INR/day): raising it to 1000 / 2000 / 3000 / 5000 gives +0.41 / +0.70 / +0.80 / +0.86pp. But a fixed minimum
spends the same rupees whether or not margin exists: fixed 3000 missed the ROAS floor (void score) in 1 of 20 unseen worlds (seed 1002,
margin -0.015); fixed 2000 survived that world with margin 0.047.

**Proposed rule** (prototype: `experiments/lib/switchable_policy.py::StateMin`, tested):
```
run 1:      allowance = max(schedule_slice, 300, 1500)               # nothing banked yet; fixed run-1 minimum
run >= 2:   allowance = max(schedule_slice, 300, min(3000, 1.0 * headroom_inr_day))   # extra spend only where margin is banked
```
(set `params.headroom_min_allowance_inr_day` to the harness's own 300 and apply the rule in `compute_headroom`.)

**Evidence.** vs L0 (`results/x2_ablation_*.md`):
| Set | Lift | Floor | Lowest margin (L0) |
|---|---|---|---|
| fresh20 (tuning) | +0.53pp | 20/20 | 0.19 (0.20) |
| 1001-1010 (diagnostic) | +0.42pp | 10/10 | 0.119 (0.140) |
| **2001-2010 (pre-registered, run once)** | **+0.32pp (0.23..0.41), better 10/10** | **10/10** | 0.287 (0.304) |

**Expected effect:** +0.3 to +0.5pp, at L0's margin. Do not expect the tuning number (+0.53): lifts were smaller on every later set.
**Alternatives:** fixed 2000 (+0.38 to +0.70, margin down to 0.047) is the aggressive option; looser state rule `sm_r3000_c4.0`
(+0.43 to +0.62, margin down to 0.057). Fixed 3000 is not recommended (1 miss in 20).
**Risks / limits:** dev-structure worlds only; 2001-2010 had no thin-margin world, so the safety evidence rests on seeds 1002/1008;
X7.3 (perturbed worlds, eval-like shocks) has not confirmed it yet. Confirm on a fresh set (e.g. 3001-3010) after adopting.

## H2. Keep cuts  — recommendation not to change
Cuts are 78% of actions and the least efficient per rupee within their week (0.75 offtake per rupee; marginal direct ROAS 1.25 against a floor
of ~4.34). That is the point: they remove the lowest-ROAS spend, lifting portfolio ROAS so raises are affordable. Removing cuts gives +0.05pp
(CI spans 0) on fresh20 and breaks the floor in 2/20 worlds; removing cuts *and* the gate gives +1.06pp but meets the floor in only 11/20.
An earlier reading that "cuts are net-negative" came from a small sample and is retracted. Do not simplify the policy by dropping cuts.

## H3. Make the guardrail projection honest about spend  — recommended, medium confidence
**Problem.** G8 never trimmed anything (442 proposed = 442 shipped over dev6), and projected spend change is 1.5-4x too low at the margin
(true/projected: budget raise 3.95x, CPM raise 1.47x, CPM cut 2.18x; X3.3). A guardrail that projects optimistically cannot catch the
over-spend that a fixed minimum allows. Today the cap on banked headroom (H1) does the safety work G8 should.
**Change:** calibrate `project_actions` spend deltas with measured factors by action type (or use the observed spend response), then re-run the
X2 gate arms to see whether G8 starts to bind. **Limit:** factors come from within-week effects on 6 dev worlds; X3.1 should confirm the shape first.

## H4. Choose the offtake/floor trade-off deliberately  — decision
W0: the old harness (0b73557) gave +0.824% over baseline; the `483ea9e` fixes (sizing respects the allowance, min allowance, precheck first)
give +0.234%, a cost of -0.59pp (CI 0.40..0.78, 6/6 seeds), because the allowance now binds and is too tight. The old behaviour was
effectively "no gate". The gate is safe but leaves 46-105k INR of banked slack unused per world. H1 recovers part of it. Decide the target
margin explicitly (e.g. keep >= 0.10 above the floor in every world) and tune to it; the frontier analysis in
`runtime_constraints_workaround/PLAN.md` item 3b is the tool.

## H5. Module fixes (after diagnosis)
| Module | Measured weakness (X1) | Proposed next step |
|---|---|---|
| Grid forecast | live-bid spend over-forecast ~1.7x on untouched campaigns (real/pred 0.60 spend, 0.51 revenue); likely assumes the best slot with certainty | confirm cause with X3.1, then model slot shares instead of the best affordable slot |
| Incrementality iota | within-type correlation with truth ~0 (brand 0.02, competition 0.03, generic -0.07); biased high for brand (+0.12) and generic (+0.14); no better with more data | oracle-iota arm first: only fix if accurate iota changes decisions; otherwise use type-level estimates |
| Sibling leader | right in 70% of clear markets, 56% of near-ties | treat flags near ties as low-confidence; do not hold followers on them |
| Shock detector | OSA recall/precision 1.00; price recall 0.43 / precision 0.08; demand recall 0.12; detection always 7 days late | gate L2 on OSA only; do not rely on price/demand flags |
| Headroom | allowance 300 -> 966 INR/day while banked headroom reaches 6.6k | covered by H1 |
| Precheck | passes nothing the guardrails block (0/442); 130 dropped | measure the false-negative side before relying on it |

## H6. Smaller documentation / hygiene items
- State in the headroom docstring that extra spend is assumed to earn zero revenue (conservative) and that the schedule fractions apply to
  the *recomputed remaining* slack, so effective spend is lower than the schedule suggests (critique A8).
- The non-front-loaded branch divides by `7 - run + 1`; the window has 6 runs.
