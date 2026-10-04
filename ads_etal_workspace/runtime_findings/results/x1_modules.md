# X1 — modules scored against truth (L0, dev worlds, 6 seeds)

## X1.1 Live-bid forecast vs the realised week

Only campaigns with no shipped action that run (so the forecast is of an unchanged bid). `real/pred` < 1 = the grid over-forecasts. `ran_out` = the campaign hit its budget that week (the grid forecasts unconstrained demand).

| stratum | pred_spend | real_spend | pred_rev | real_rev | spend_real/pred | rev_real/pred |
|---|---|---|---|---|---|---|
| not_run_out | 404063.930 | 240279.270 | 2719193.370 | 1386162.143 | 0.595 | 0.510 |
| ran_out | 213314.510 | 105442.753 | 1091714.150 | 531944.571 | 0.494 | 0.487 |

By tier:

| stratum | tier | cell_runs | pred_spend | real_spend | pred_rev | real_rev | spend_real/pred | rev_real/pred | droas_real | droas_pred |
|---|---|---|---|---|---|---|---|---|---|---|
| not_run_out | A | 1241 | 371330.510 | 221398.743 | 2559282.880 | 1318868.286 | 0.596 | 0.515 | 5.957 | 6.892 |
| not_run_out | B | 295 | 27719.430 | 15952.657 | 131773.310 | 59890.857 | 0.576 | 0.454 | 3.754 | 4.754 |
| not_run_out | C | 105 | 5013.990 | 2927.870 | 28137.180 | 7403.000 | 0.584 | 0.263 | 2.528 | 5.612 |
| ran_out | A | 602 | 189215.880 | 95592.260 | 1028514.500 | 509257.571 | 0.505 | 0.495 | 5.327 | 5.436 |
| ran_out | B | 134 | 22503.880 | 9138.946 | 57890.340 | 21081.286 | 0.406 | 0.364 | 2.307 | 2.572 |
| ran_out | C | 16 | 1594.750 | 711.547 | 5309.310 | 1605.714 | 0.446 | 0.302 | 2.257 | 3.329 |

## X1.2 Incrementality estimate vs truth

`inc_eff` = true incrementality x organic damping, the quantity ι estimates.

| type | n | mean_est | mean_true_inc | mean_true_eff | mae_vs_eff | bias_vs_eff | corr_eff |
|---|---|---|---|---|---|---|---|
| brand | 180 | 0.238 | 0.141 | 0.116 | 0.173 | 0.122 | 0.020 |
| competition | 144 | 0.815 | 0.855 | 0.855 | 0.181 | -0.040 | 0.033 |
| generic | 180 | 0.683 | 0.578 | 0.543 | 0.195 | 0.140 | -0.071 |

By run (does the estimate improve with data?):

| run | n | mae_vs_eff | bias |
|---|---|---|---|
| 1 | 84 | 0.198 | 0.097 |
| 2 | 84 | 0.180 | 0.065 |
| 3 | 84 | 0.170 | 0.065 |
| 4 | 84 | 0.194 | 0.100 |
| 5 | 84 | 0.185 | 0.082 |
| 6 | 84 | 0.171 | 0.085 |

## X1.3 Sibling leader vs true value per impression

| near_tie | markets | leader_correct | mean_value_ratio |
|---|---|---|---|
| False | 1259 | 0.701 | 0.920 |
| True | 181 | 0.564 | 0.880 |

## X1.4 Headroom and allowance vs what was left

`headroom_inr_day`: spend/day the floor could absorb at zero marginal ROAS. `end_slack_inr_total`: the same quantity left unspent at the end of the window (₹, whole window).

| run | headroom_inr_day | allowance_inr_day | shipped_raise_pred_dspend |
|---|---|---|---|
| 1 | 0.000 | 300.000 | 218.400 |
| 2 | 913.500 | 303.300 | 219.100 |
| 3 | 1827.400 | 408.800 | 218.400 |
| 4 | 3064.100 | 612.800 | 498.800 |
| 5 | 4831.400 | 966.300 | 679.600 |
| 6 | 6644.200 | 6644.200 | 2690.900 |

| seed | end_slack_inr_total | end_margin |
|---|---|---|
| 7 | 62346.200 | 0.370 |
| 11 | 104823.410 | 0.540 |
| 23 | 80828.010 | 0.420 |
| 42 | 81679.130 | 0.540 |
| 101 | 45613.340 | 0.240 |
| 202 | 70331.260 | 0.430 |

## X1.5 What precheck lets through

| proposed | shipped | blocked | dropped_by_precheck |
|---|---|---|---|
| 442 | 442 | 0 | 130 |

## X1.6 Shock detection vs injected shocks

| kind | tp | fn | fp_before_onset | fp_elsewhere | recall | precision |
|---|---|---|---|---|---|---|
| demand | 14 | 105 | 4 | 38 | 0.118 | 0.250 |
| osa | 24 | 0 | 0 | 0 | 1.000 | 1.000 |
| price | 19 | 25 | 4 | 208 | 0.432 | 0.082 |

| seed | kind | onset_day | first_detect_obs_day | lead_days |
|---|---|---|---|---|
| 7 | demand | 56 | 63 | 7 |
| 7 | osa | 42 | 49 | 7 |
| 7 | price | 49 | 56 | 7 |
| 11 | demand | 56 | 63 | 7 |
| 11 | osa | 42 | 49 | 7 |
| 11 | price | 49 | 63 | 14 |
| 23 | demand | 56 | 63 | 7 |
| 23 | osa | 42 | 49 | 7 |
| 23 | price | 49 | 56 | 7 |
| 42 | demand | 56 | 63 | 7 |
| 42 | osa | 42 | 49 | 7 |
| 42 | price | 49 | 56 | 7 |
| 101 | demand | 56 | 63 | 7 |
| 101 | osa | 42 | 49 | 7 |
| 101 | price | 49 | 56 | 7 |
| 202 | demand | 56 | 63 | 7 |
| 202 | osa | 42 | 49 | 7 |
| 202 | price | 49 | 56 | 7 |
