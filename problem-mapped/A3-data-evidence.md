# A3 — Data evidence: E1-E10, re-derived

Companion to `A1-implementation.md`/`A2-tests-and-scenarios.md`. The plan's evidence table (E1-E10)
was originally produced by hand, in an earlier session, by reading `data/` (the baseline's own
shipped 42-day trajectory) directly. `harness_eval/probes.py` (M4) re-derives the same evidence
independently — written from the plan's one-line description of each item, reading only `data/`,
never looking at the earlier numbers while writing the probe code. This doc is the comparison.

**Run it yourself:** `make data && make probes` (the first regenerates `data/` from the baseline
policy if it's stale; the second runs the probes and writes `harness_eval/out/probes.json`).

## E1 — incrementality ordering

| | Report | Probe (`probe_e1_incrementality`) |
|---|---|---|
| brand β (cannibalisation) | −0.88 | −0.8794 |
| generic β | −0.50 | −0.4978 |
| competitor β | ≈ 0.0 | −0.0096 |
| ordering ι_brand < ι_generic < ι_competitor | holds | holds (`ordering_holds: true`) |

Method: `organic_units ~ FE(sku x city) + FE(dow) + sum_type beta_type * ad_orders_type`, fit by
`numpy.linalg.lstsq` on the full 70-day trajectory (`harness/tools/incrementality.py`). The joint
`sku x city` fixed effect (not separate `sku` and `city` dummies) was the fix that got this right
— see the M1 build-log entry for the version that got the ordering backwards.

## E2 — self-competition (siblings)

| | Report | Probe (`probe_e2_siblings`) |
|---|---|---|
| contested cells / total | 100 / 110 | 100 / 110 |
| contested markets / total | 40 / 50 | 40 / 50 |

Exact match. Uses the `run_01/{campaigns,campaign_keywords}_before.csv` snapshot (the live state
right after warm-up, before the baseline's first decision) — `data/base/*.csv` is `world.public`
at *build* time, before even warm-up, so it isn't the right snapshot for a bid-dependent read
(see `probes.py`'s module docstring). The probe additionally reports `wrong_leader_markets: 17`
— contested markets where a non-leader sibling (by `conv x ASP x iota`) holds ≥ 80% of slot 1 —
which the original report didn't quantify; a new number, not a re-derivation.

## E3 — chronically budget-starved campaigns

| | Report | Probe (`probe_e3_runouts`) |
|---|---|---|
| campaigns that ran out every warm-up day | C-S1-BLR, C-S1-DEL, C-S2-MUM, C-S3-BLR, C-S5-BLR, C-S5-DEL | the same 6, exact set |

## E4 / E5 — shock detection lead time and own-action confounding

Not a magnitude comparison — `probe_e4_e5_shock_recall` runs `tools/shocks.py`'s z-score
detector at each of the baseline's own 6 decision days and reports how many cells get flagged:

| Run | Day | Cells flagged |
|---|---|---|
| 1 | 28 | 1 |
| 2 | 35 | 35 |
| 3 | 42 | 18 |
| 4 | 49 | 19 |
| 5 | 56 | 19 |
| 6 | 63 | 17 |

**Caveat, stated plainly rather than tuned away:** this has no multiple-testing correction across
roughly 100 simultaneous z-tests per run at a z >= 2.5 threshold, so a chunk of each run's flagged
count is expected noise, not a real shock. Run 2's jump to 35 is largely the 21-day lookback
window straddling the warm-up-to-eval transition, where the market's own baseline level shifts for
reasons unrelated to any scenario shock. This is why `tools/shocks.py` feeds a *leaf's* judgment
(L2 Shock attribution) rather than triggering an action on its own — the mechanical flag is a
"look here", not a verdict. Recovering the three *specific* injected shocks in `dev.json` (S2/HYD
OSA dip at run 3, MUM K05/K06 price shock from run 4, K03/K04 demand shock from run 5) by name,
cell by cell, out of this noisier set is possible but wasn't done as a strict pass/fail check here
— flagged as a natural follow-up probe, not claimed as already verified.

## E9 — headroom and the ROAS floor

| | Report | Probe (`probe_e9_headroom`) |
|---|---|---|
| ends at (direct ROAS) | 4.97x | 4.9667x |
| floor | 4.54x | 4.5351x |
| warm-up spend/day | ₹18.9K | ₹18,919.23 |
| post-warm-up spend/day | ₹17.8K | ₹17,833.89 |

Within rounding on every figure.

## E10 — wasted (blocked) proposals

| | Report | Probe (`probe_e10_blocked_share`) |
|---|---|---|
| G3 top-slot blocks | 27 | 28 blocked guardrail-log rows (not all G3 specifically — see below) |
| blocked share of proposed | not stated as a %, this is new | 28 / 176 = **15.9%** |

One precision note: the probe counts *all* blocked guardrail-log rows (`outcome == "blocked"`,
any rule — G0/G3/G4/G5/G7), not G3 specifically, so 28 isn't a direct like-for-like count against
the report's "27 G3 blocks" — it's close by coincidence of magnitude, not because it's measuring
the identical thing. The per-run breakdown (`probe_e10_blocked_share`'s `per_run`) is in
`harness_eval/out/probes.json` if a rule-by-rule breakdown is needed later.

## What this independent recovery is (and isn't) evidence of

It's evidence that `harness/tools/{incrementality,siblings,shocks,headroom}.py` compute what they
claim to compute, checked against a real dataset neither the tools' authors nor this doc's numbers
came from circularly. It is **not** evidence about the *eval* scenario — E1-E10 are all dev-scenario
facts, and the dev/eval scenarios differ (different shocks, different seed, per `gpc/world.py`'s
own docstring). `harness_eval/worlds.py`'s held-out seeds and perturbed scenarios (P1-P6) are the
mechanism for checking robustness beyond dev specifics; this doc's job was narrower — confirming
the measurement tools themselves are correct on data everyone already agrees is real.
