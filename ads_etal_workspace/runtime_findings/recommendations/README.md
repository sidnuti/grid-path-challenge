# Recommendations: index

> **Provenance note (2026-10-03).** The first version of this README (a priority table) was accidentally overwritten while a second session
> was adding files here. This index was rebuilt from the summary table in `RECOMMENDATIONS.md`, which is the detailed source. If you remember
> content that was in the old README and is not here, `RECOMMENDATIONS.md` and the companion files below are the places to look.

Every recommendation comes from a measured result (`../FINDINGS.md`, `../results/`, `../../logs/2026-10-03-experiments-log.md`). `harness/`, `gpc/` and
`harness_eval/` are owned by another session and were not edited; items touching them are addressed to that session.

| File | What it is |
|---|---|
| `RECOMMENDATIONS.md` | the detailed source: R1-R12 with evidence, recommendation, limits |
| `01-harness-changes.md` | proposed changes to `harness/` (H1 onwards; the first is the state-dependent minimum allowance), not applied |
| `02-llm-layer.md` | LLM layer: do not run the paid slice as configured, with the X5.1 table |
| `03-next-experiments.md` | prioritised next experiments (E1 onwards) and their limits; next untouched seed set 3001-3010 |
| `04-measurement-practice.md` | measurement and process rules learned during this work |

## Summary table

| # | Recommendation | For | Priority | Status | Expected effect |
|---|---|---|---|---|---|
| R1 | Relax the headroom gate through a **state-dependent minimum allowance**; do **not** use a fixed 3000 INR/day minimum | harness | P0 | **confirmed** (2001-2010: +0.32pp, floor 10/10; see R1) | +0.3 to +0.5pp offtake at L0's floor margin |
| R2 | **Keep cuts**; if anything, order them by lowest marginal ROAS first | harness | P0 | confirmed (keep) / hypothesis (ordering) | avoids 2/20-9/20 floor misses |
| R3 | Treat the 2026-10-03 sizing fix as a **deliberate trade-off**, not a free fix: it cost ~0.6pp | harness, docs | P0 | confirmed (W0) | correct reading of +0.82% -> +0.23% |
| R4 | **Correct the spend projections** used by the guardrails and the gate (level over-forecast ~1.7x; marginal under-projection 1.5-4x) | harness | P1 | supported; mechanism pending X3.1 | fewer floor surprises when the gate is relaxed |
| R5 | **Don't run the paid LLM slice as configured**; redesign triggers and what the leaves decide first | harness, plan | P1 | supported (X5.1, 6 worlds) | saves spend that cannot move offtake today |
| R6 | **Remove or restrict the L6 veto** (and keep L4 explore off) | harness | P1 | supported (X5.1) | +0.03..0.14pp vs vetoing; no downside seen |
| R7 | **Fix the ι estimator only if it changes decisions**: run the oracle-ι test first, then add OSA and search-prior controls | experiments, then harness | P2 | hypothesis | unknown; measured accuracy is ~0 within type |
| R8 | **Shock detector**: control false positives on price shocks; aggregate keyword-wide for demand shocks | harness | P2 | supported (X1.6) | precision 0.08 -> ? ; recall 0.12 -> ? |
| R9 | **Deprioritise sibling-leader fixes** | harness | P3 | supported (X1.3 + X5.1) | none expected (oracle leader choice adds 0) |
| R10 | **Measurement standards**: t-CIs, lift vs no-op, floor margin in every table, fresh seeds, code hash | harness_eval, reports | P1 | confirmed (applied in experiments) | prevents the overstated readings we hit |
| R11 | **Update stale documents** (paper rev 5, deep dive rev 3, critique status, runtime report) | docs | P1 | confirmed | numbers match the current code |
| R12 | **Next experiments**: offtake-vs-margin frontier, oracle-ι, generalisation | experiments | P1 | planned | decides R1/R4/R7 settings |

Status key: **confirmed** = replicated on worlds not used to choose it; **supported** = measured, not yet confirmed; **pending** = waits on a running experiment; **hypothesis** = untested.
