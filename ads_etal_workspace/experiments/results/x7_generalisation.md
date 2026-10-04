# X7.3 — generalisation to perturbed worlds

13 worlds x 3 seeds (303-305). Lift in % vs full L0 on the same world+seed (t-CI over world x seed pairs; pairs within a scenario share its parameters, so the CIs are optimistic).

| family | arm | n_worlds | vs_l0_pct | t95 | worse/better | floor_met | min_margin | vs_no_op_pct |
|---|---|---|---|---|---|---|---|---|
| shock | gate_min3000 | 18 | 0.792 | 0.66 … 0.92 | 0/18 | 18/18 | 0.012 | 0.894 |
| shock | l0 | 18 | 0.000 | 0.00 … 0.00 | 0/0 | 18/18 | 0.065 | 0.100 |
| shock | no_cuts | 18 | -0.021 | -0.14 … 0.10 | 11/7 | 12/18 | -0.277 | 0.079 |
| shock | no_headroom_gate | 18 | 0.801 | 0.67 … 0.93 | 0/18 | 18/18 | 0.009 | 0.902 |
| shock | no_op | 18 | -0.100 | -0.24 … 0.04 | 12/6 | 11/18 | -0.312 | 0.000 |
| shock | sm_r1500_c1.0 | 18 | 0.574 | 0.46 … 0.69 | 0/18 | 18/18 | 0.060 | 0.675 |
| value | gate_min3000 | 21 | 0.762 | 0.59 … 0.93 | 0/21 | 20/21 | -0.019 | 0.880 |
| value | l0 | 21 | 0.000 | 0.00 … 0.00 | 0/0 | 21/21 | 0.113 | 0.117 |
| value | no_cuts | 21 | -0.028 | -0.13 … 0.07 | 13/8 | 21/21 | 0.007 | 0.088 |
| value | no_headroom_gate | 21 | 0.785 | 0.61 … 0.96 | 0/21 | 20/21 | -0.038 | 0.903 |
| value | no_op | 21 | -0.116 | -0.24 … 0.01 | 15/6 | 19/21 | -0.013 | 0.000 |
| value | sm_r1500_c1.0 | 21 | 0.509 | 0.41 … 0.61 | 0/21 | 21/21 | 0.089 | 0.627 |

Mean lift vs L0 by scenario:

| scenario | gate_min3000 | no_cuts | no_headroom_gate | no_op | sm_r1500_c1.0 |
|---|---|---|---|---|---|
| P1_osa_different_sku_city | 0.750 | -0.040 | 0.750 | -0.110 | 0.560 |
| P2_price_different_market_bigger | 0.910 | 0.090 | 0.920 | -0.010 | 0.670 |
| P3_demand_different_keywords_earlier | 0.730 | -0.040 | 0.740 | -0.110 | 0.540 |
| P4_all_three_shifted_earlier | 0.850 | -0.070 | 0.860 | -0.110 | 0.540 |
| P5_severe_osa_dip | 0.790 | -0.020 | 0.800 | -0.100 | 0.600 |
| P6_demand_shock_on_brand | 0.720 | -0.040 | 0.730 | -0.150 | 0.530 |
| V_appeal_rot | 0.730 | -0.090 | 0.730 | -0.190 | 0.570 |
| V_intent_hi | 1.080 | -0.030 | 1.120 | -0.170 | 0.530 |
| V_intent_lo | 0.420 | 0.010 | 0.420 | -0.040 | 0.320 |
| V_iota_hi | 0.950 | -0.100 | 0.960 | -0.190 | 0.640 |
| V_iota_lo | 0.560 | -0.020 | 0.570 | -0.030 | 0.420 |
| V_sigma_hi | 0.550 | -0.040 | 0.590 | -0.240 | 0.330 |
| V_sigma_lo | 1.050 | 0.080 | 1.100 | 0.050 | 0.740 |

Floor misses:

| scenario | arm | floor_misses |
|---|---|---|
| P2_price_different_market_bigger | no_cuts | 3 |
| P2_price_different_market_bigger | no_op | 3 |
| P4_all_three_shifted_earlier | no_cuts | 3 |
| P4_all_three_shifted_earlier | no_op | 3 |
| P5_severe_osa_dip | no_op | 1 |
| V_appeal_rot | no_op | 1 |
| V_intent_hi | gate_min3000 | 1 |
| V_intent_hi | no_headroom_gate | 1 |
| V_intent_hi | no_op | 1 |
