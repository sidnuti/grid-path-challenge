<!-- code hashes: 63196db22b74 -->
# X3.3 — causal effect of each shipped action (L0)

321 actions across seeds [7, 11, 23, 42], every run. Effects are within the action's own week, from an exact paired re-simulation with that one action removed.

## By action type

| action_type | n | true_dspend_sum | pred_dspend_sum | true_dspend_ratio | true_dspend_corr | true_drev_sum | pred_drev_sum | true_drev_ratio | true_drev_corr | true_dofftake_sum | offtake_per_rupee | adrev_per_rupee |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| increase_budget | 32.000 | 40717.940 | 10297.990 | 3.954 | 0.666 | 164320.000 | 55556.320 | 2.958 | 0.395 | 71770.000 | 1.763 | 4.036 |
| increase_cpm | 39.000 | 9430.610 | 6406.240 | 1.472 | 0.220 | 40990.000 | 44251.830 | 0.926 | 0.019 | 29630.000 | 3.142 | 4.346 |
| reduce_cpm | 250.000 | -96455.680 | -44281.350 | 2.178 | 0.291 | -120454.000 | -117090.520 | 1.029 | 0.238 | -72454.000 | 0.751 | 1.249 |

## By method

| method | n | true_dspend_sum | pred_dspend_sum | true_dspend_ratio | true_dspend_corr | true_drev_sum | pred_drev_sum | true_drev_ratio | true_drev_corr | true_dofftake_sum | offtake_per_rupee | adrev_per_rupee |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M_Base | 250.000 | -96455.680 | -44281.350 | 2.178 | 0.291 | -120454.000 | -117090.520 | 1.029 | 0.238 | -72454.000 | 0.751 | 1.249 |
| M_Budget | 32.000 | 40717.940 | 10297.990 | 3.954 | 0.666 | 164320.000 | 55556.320 | 2.958 | 0.395 | 71770.000 | 1.763 | 4.036 |
| M_Reprice | 39.000 | 9430.610 | 6406.240 | 1.472 | 0.220 | 40990.000 | 44251.830 | 0.926 | 0.019 | 29630.000 | 3.142 | 4.346 |

## Sizing rank check (raises only, n=70)

Spearman correlation between the projected marginal ratio (Δrev/Δspend) and the true marginal offtake per rupee: **0.406**.

