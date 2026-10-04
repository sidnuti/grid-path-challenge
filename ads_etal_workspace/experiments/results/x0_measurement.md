<!-- code hashes: 63196db22b74 -->
# X0 — measurement checks

## X0.1 Do the books balance?

18 of 18 (arm × seed) runs pass every identity. Zero-organic rows are days where `organic − cannibalised` was clipped at 0, i.e. hidden cannibalisation.

| arm | runs | all_pass | max_offtake_err | max_unit_err | zero_organic_rows |
|---|---|---|---|---|---|
| baseline | 6 | True | 0.000 | 0 | 234 |
| l0 | 6 | True | 0.000 | 0 | 301 |
| no_op | 6 | True | 0.000 | 0 | 309 |

## X0.2 Does the oracle reconstruct what the market served?

Clean auctions only (no sibling in the market ran out of budget). `impr_lost_to_budget_share` is the share of *potential* impressions never served because budgets ran out (all auctions).

| seed | day | rows_clean | rows_all | share_clean | max_abs_err | p99_abs_err | missing_in_emitted | impr_lost_to_budget_share |
|---|---|---|---|---|---|---|---|---|
| 7 | 3 | 673 | 1556 | 0.432 | 0.000 | 0.000 | 0 | 0.105 |
| 7 | 20 | 526 | 1588 | 0.331 | 0.000 | 0.000 | 0 | 0.128 |
| 7 | 30 | 727 | 1551 | 0.469 | 0.000 | 0.000 | 0 | 0.073 |
| 7 | 41 | 534 | 1597 | 0.334 | 0.000 | 0.000 | 0 | 0.133 |
| 7 | 50 | 1115 | 1554 | 0.718 | 0.000 | 0.000 | 0 | 0.074 |
| 7 | 62 | 723 | 1572 | 0.460 | 0.000 | 0.000 | 0 | 0.081 |
| 101 | 3 | 506 | 1505 | 0.336 | 0.000 | 0.000 | 0 | 0.112 |
| 101 | 20 | 344 | 1528 | 0.225 | 0.000 | 0.000 | 0 | 0.146 |
| 101 | 30 | 519 | 1505 | 0.345 | 0.000 | 0.000 | 0 | 0.079 |
| 101 | 41 | 358 | 1527 | 0.234 | 0.000 | 0.000 | 0 | 0.109 |
| 101 | 50 | 653 | 1492 | 0.438 | 0.000 | 0.000 | 0 | 0.061 |
| 101 | 62 | 443 | 1527 | 0.290 | 0.000 | 0.000 | 0 | 0.090 |

## X0.3 Noise floor and minimum detectable effect

A/A difference (same arm twice): **0.0 ₹**.

| comparison | n | mean_pct | sd_pct | min | max | ci95 | MDE n=6 | MDE n=12 | MDE n=24 | worlds for 0.1pp | worlds for 0.2pp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| l0_vs_baseline | 6 | 0.234 | 0.156 | 0.097 | 0.455 | 0.07 … 0.40 | 0.179 | 0.126 | 0.089 | 20 | 5 |
| l0_vs_no_op | 6 | 0.069 | 0.115 | -0.062 | 0.199 | -0.05 … 0.19 | 0.132 | 0.093 | 0.066 | 11 | 3 |
| baseline_vs_no_op | 6 | -0.165 | 0.185 | -0.405 | 0.091 | -0.36 … 0.03 | 0.212 | 0.150 | 0.106 | 27 | 7 |

## X0.4 Where does the lift come from?

Mean over seeds of (l0 − reference), ₹ over the 42 evaluation days.

| vs | offtake | ad_value | organic_value | spend |
|---|---|---|---|---|
| baseline | 40,454 | 80,814 | -40,360 | 31,755 |
| no_op | 11,826 | 60,932 | -49,105 | -47,306 |

By keyword type (true-incremental view), mean over seeds:

| vs | keyword_type | d_spend | d_ad_orders | d_incr_units | d_cannibalised |
|---|---|---|---|---|---|
| baseline | brand | 8,061.5 | 219.7 | 23.5 | 196.1 |
| baseline | competition | 5,036.9 | 15.0 | 13.1 | 1.9 |
| baseline | generic | 18,656.7 | 139.7 | 73.8 | 65.9 |
| no_op | brand | 2,158.8 | 193.8 | 23.1 | 170.8 |
| no_op | competition | -12,503.3 | -27.3 | -23.3 | -4.0 |
| no_op | generic | -36,961.4 | -285.5 | -149.1 | -136.4 |

Direct vs. true iROAS and funnel metrics by keyword type (mean over seeds):

| arm | keyword_type | direct_roas | true_iroas | orders_per_1k_impr | avg_cpm | incrementality |
|---|---|---|---|---|---|---|
| baseline | brand | 17.431 | 1.939 | 15.567 | 187.409 | 0.106 |
| baseline | competition | 1.283 | 1.096 | 2.349 | 392.626 | 0.853 |
| baseline | generic | 4.257 | 2.339 | 5.718 | 275.825 | 0.534 |
| l0 | brand | 16.310 | 1.846 | 15.661 | 200.618 | 0.107 |
| l0 | competition | 1.317 | 1.126 | 2.364 | 400.099 | 0.854 |
| l0 | generic | 4.155 | 2.283 | 5.752 | 284.511 | 0.534 |
| no_op | brand | 16.040 | 1.802 | 15.648 | 201.235 | 0.106 |
| no_op | competition | 1.242 | 1.062 | 2.342 | 412.338 | 0.854 |
| no_op | generic | 3.871 | 2.125 | 5.654 | 291.518 | 0.533 |

## X0.5 Lift by week

| week | l0_vs_baseline_pct mean | l0_vs_baseline_pct min | l0_vs_baseline_pct max | l0_vs_no_op_pct mean | l0_vs_no_op_pct min | l0_vs_no_op_pct max | cum_l0_vs_baseline_pct mean | cum_l0_vs_baseline_pct min | cum_l0_vs_baseline_pct max |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.061 | -0.324 | 0.678 | 0.022 | -0.110 | 0.080 | 0.061 | -0.324 | 0.678 |
| 2 | -0.039 | -0.694 | 0.506 | 0.012 | -0.178 | 0.186 | 0.011 | -0.477 | 0.544 |
| 3 | -0.004 | -0.382 | 0.409 | -0.058 | -0.289 | 0.241 | 0.006 | -0.327 | 0.443 |
| 4 | 0.245 | -0.077 | 0.586 | -0.091 | -0.169 | 0.001 | 0.065 | -0.180 | 0.368 |
| 5 | 0.300 | 0.187 | 0.450 | 0.080 | -0.043 | 0.259 | 0.112 | -0.061 | 0.342 |
| 6 | 0.846 | 0.652 | 1.075 | 0.446 | 0.026 | 0.805 | 0.234 | 0.097 | 0.455 |

## X0.6 Floor margin (a missed floor voids the score)

Margin = direct ROAS − floor, ROAS points, over the 6 dev worlds.

| arm | floor_met | mean_margin | min_margin | mean_floor_safe_offtake_per_day |
|---|---|---|---|---|
| no_op | 6/6 | 0.076 | 0.009 | 411896.333 |
| baseline | 6/6 | 0.518 | 0.287 | 411214.667 |
| l0 | 6/6 | 0.422 | 0.244 | 412177.833 |

