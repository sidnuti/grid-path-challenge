# P2 results: sim v2 Modules B, C, D, public tables, scenarios

Full tables: `readout.md` and the `readout_<scenario>.csv` files (seeds 7, 11, 23). The starting set-up is held after warm-up, and probes bypass guardrails. Log: `../../logs/P2_log.md`.

## Mechanisms and traps

| Mechanism / trap (doc 02) | Measured (seeds 7 / 11 / 23) | Gate |
|---|---|---|
| Category cannibalization (sc1) | sibling share of ad orders: K03 0.19–0.20, K01 0.44–0.49 | sibling share > 0.1 ✓ |
| "Butter ≈ Amul": K07 labelled generic but Aurel-owned (sc2) | K07 direct ROAS 9.9–12.0 vs generic 3.5–3.7; ι^brand K07 0.18–0.20 vs K03 0.57 | ι^brand K07 < ½ K03, direct ROAS > 2× generic ✓ |
| Challenger query K05 owned by Nimbus (sc2) | ι^brand 0.71–0.73 (vs K03 0.57) | > K03 ✓ |
| Pause K01 → conquest (sc2) | conquest in all 5 cities from day 31; offtake lost ₹232–453k vs spend saved ₹67–74k | lost > 2× saved ✓ |
| No conquest while defended (sc2) | 0 conquest days under the starting bids | ✓ |
| Reformulation illusion: pause K03 (sc2) | K01 impressions +6–12%, K01 attributed revenue +5–6%, brand offtake −2.4 to −3.4% | ✓ |
| Festive CPM inflation (sc3) | K03 clearing-price multiplier at peak / pre-window = 1.456; back to 1.0 by day 69 | in [1.3, 1.5] ✓ |
| Pull-forward (sc3) | Σ dip = ρ·Σ excess exactly; dip on days 60–69 | ✓ |
| Finite stock (sc3) | stock never negative; S6 stock-out in 0–1 cities at day 58 under starting bids; OSA 0 afterwards | ✓ |
| Holdout readout | 95% CI covers the truth in ≥ 90% of 50 seeds | ✓ |

## Brand iROAS, starting set-up held for 6 runs

| Scenario | iROAS (7 / 11 / 23) | Why it differs from sc1 |
|---|---|---|
| dev (legacy ι) | 1.73 / 1.65 / 1.82 | — |
| sc1_cannibal | 1.81 / 1.79 / 1.68 | the shelf replaces fixed ι |
| sc2_brand_assoc | 2.20 / 2.19 / 2.03 | K01 defence against opportunistic conquest counts as incremental |
| sc3_festive | 1.74 / 1.74 / 1.68 | festive CPMs ×1.46; S6 salvage |
| sc4_seasonal | 1.85 / 1.78 / 1.72 | K12 added |
| sc_all | 2.15 / 2.15 / 2.09 | everything |

## Calibration
Warm-up values for every scenario and seed:

| Metric | Range |
|---|---|
| Direct ROAS, generic keywords | 3.5–3.8 |
| Direct ROAS, competitor keywords | 1.1–1.35 |
| Direct ROAS, brand keywords | 13.6–16.8 |
| Ad share of units | 0.17–0.21 |
| Run-out share (legacy campaigns) | 0.28–0.34 |

Brand direct ROAS on seeds 11 and 23 is below CALIBRATION.md's 16–19, identically in legacy dev (README M6).
