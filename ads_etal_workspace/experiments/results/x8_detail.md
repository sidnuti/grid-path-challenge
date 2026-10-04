<!-- code hashes: 4f8b8d70cdcb, 951690e77e25, 9b13104d1e6c, c6db3cafe0e1  (MIXED) -->
# X8 detail: what the real-LLM arms did (cached worlds so far)

Model qwen/qwen3.7-flash via OpenRouter, reasoning on. Paired vs `l0` and `baseline` in the same world. $ repriced from tokens at list price ($0.03 / $0.13 per M).

## Replicate 0, paired over worlds (t-CI, exact sign-flip p)

| arm | worlds | mean_vs_l0 | ci95 | p_signflip | better | mean_spend_vs_l0 | mean_margin | mean_l0_margin |
|---|---|---|---|---|---|---|---|---|
| l12_llm | 6 | 0.011 | -0.02 … 0.04 | 1.000 | 1 | 0.160 | 0.421 | 0.422 |
| l2p_aug_llm | 6 | -0.092 | -0.32 … 0.13 | 0.375 | 2 | -6.409 | 0.751 | 0.422 |
| l2p_nat_llm | 6 | -0.420 | -0.89 … 0.05 | 0.125 | 2 | -6.632 | 0.556 | 0.422 |

## Where L2′ moved spend vs L0 (eval window, ₹/day)

| arm | seed | Δ₹/d brand | Δ₹/d competition | Δ₹/d generic | Δ₹/d S1 | Δ₹/d S2 | Δ₹/d S3 | Δ₹/d S4 | Δ₹/d S5 |
|---|---|---|---|---|---|---|---|---|---|
| l2p_aug_llm | 7 | -197.000 | -354.000 | -1120.000 | 26.000 | -406.000 | -1490.000 | 474.000 | -276.000 |
| l2p_aug_llm | 11 | -49.000 | -1795.000 | 227.000 | -53.000 | 775.000 | -2100.000 | 182.000 | -420.000 |
| l2p_aug_llm | 23 | -131.000 | -439.000 | -315.000 | -231.000 | -71.000 | -761.000 | 298.000 | -119.000 |
| l2p_aug_llm | 42 | -180.000 | -149.000 | -961.000 | -387.000 | -97.000 | -472.000 | -57.000 | -278.000 |
| l2p_aug_llm | 101 | -168.000 | -158.000 | -253.000 | 596.000 | 332.000 | -1004.000 | -127.000 | -376.000 |
| l2p_aug_llm | 202 | -167.000 | -158.000 | -710.000 | 338.000 | -143.000 | -960.000 | 250.000 | -518.000 |
| l2p_nat_llm | 7 | -150.000 | -277.000 | 181.000 | 368.000 | -290.000 | -839.000 | 410.000 | 104.000 |
| l2p_nat_llm | 11 | -118.000 | -1493.000 | 992.000 | -127.000 | -162.000 | -981.000 | 471.000 | 180.000 |
| l2p_nat_llm | 23 | -107.000 | 49.000 | -1399.000 | -1021.000 | -317.000 | -312.000 | 39.000 | 155.000 |
| l2p_nat_llm | 42 | -196.000 | -310.000 | -171.000 | 127.000 | -310.000 | -296.000 | -254.000 | 57.000 |
| l2p_nat_llm | 101 | -395.000 | -347.000 | -2263.000 | -1266.000 | 304.000 | -1499.000 | -224.000 | -320.000 |
| l2p_nat_llm | 202 | -161.000 | 159.000 | -1575.000 | 766.000 | -39.000 | -1846.000 | 145.000 | -602.000 |

## Summary by arm (all replicates)

| arm | worlds | vs_l0_mean | vs_l0_min | vs_l0_max | better | floor_met | min_margin | usd_per_world | llm_min_per_world | calls_per_world | default_share |
|---|---|---|---|---|---|---|---|---|---|---|---|
| l12_llm | 8 | 0.009 | -0.005 | 0.076 | 1 | 8 | 0.244 | 0.008 | 8.529 | 37.375 | 0.000 |
| l2p_aug_llm | 6 | -0.092 | -0.428 | 0.144 | 2 | 6 | 0.600 | 0.025 | 19.116 | 12.000 | 0.014 |
| l2p_nat_llm | 6 | -0.420 | -1.004 | 0.118 | 2 | 6 | 0.420 | 0.024 | 18.173 | 12.000 | 0.014 |

## Per world

| arm | rep | seed | vs_l0_pct | vs_baseline_pct | droas | floor_met | margin | l0_margin | spend_vs_l0_pct | ad_units_vs_l0_pct | organic_vs_l0_pct | llm_calls | defaults | usd | llm_wall_s | shipped | fallback_runs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| l2p_aug_llm | 0 | 7 | -0.186 | -0.089 | 5.407 | True | 0.872 | 0.366 | -9.096 | -8.677 | 1.536 | 12 | 0 | 0.024 | 593.427 | 155 | 0 |
| l2p_aug_llm | 0 | 11 | 0.144 | 0.272 | 4.994 | True | 0.988 | 0.539 | -8.714 | -1.886 | 0.133 | 12 | 0 | 0.027 | 1140.063 | 186 | 0 |
| l2p_aug_llm | 0 | 23 | -0.139 | -0.038 | 4.774 | True | 0.684 | 0.418 | -4.697 | -4.671 | 0.643 | 12 | 0 | 0.024 | 1196.369 | 175 | 0 |
| l2p_aug_llm | 0 | 42 | -0.428 | -0.037 | 5.379 | True | 0.658 | 0.536 | -7.528 | -4.403 | 0.406 | 12 | 0 | 0.028 | 1442.751 | 183 | 0 |
| l2p_aug_llm | 0 | 101 | 0.123 | 0.352 | 5.097 | True | 0.600 | 0.244 | -2.891 | -0.801 | 0.224 | 12 | 0 | 0.023 | 1106.110 | 154 | 0 |
| l2p_aug_llm | 0 | 202 | -0.069 | 0.386 | 5.535 | True | 0.705 | 0.432 | -5.525 | -4.558 | 0.838 | 12 | 1 | 0.023 | 1402.966 | 155 | 0 |
| l2p_nat_llm | 0 | 7 | 0.118 | 0.215 | 5.138 | True | 0.603 | 0.366 | -1.343 | -3.622 | 0.797 | 12 | 0 | 0.024 | 625.858 | 126 | 0 |
| l2p_nat_llm | 0 | 11 | 0.046 | 0.174 | 4.664 | True | 0.658 | 0.539 | -3.336 | -1.628 | 0.140 | 12 | 0 | 0.024 | 1015.689 | 141 | 0 |
| l2p_nat_llm | 0 | 23 | -0.813 | -0.713 | 4.576 | True | 0.486 | 0.418 | -7.734 | -7.643 | 0.833 | 12 | 0 | 0.024 | 1253.406 | 120 | 0 |
| l2p_nat_llm | 0 | 42 | -0.436 | -0.044 | 5.141 | True | 0.420 | 0.536 | -3.948 | -3.847 | 0.479 | 12 | 1 | 0.026 | 1301.608 | 130 | 0 |
| l2p_nat_llm | 0 | 101 | -1.004 | -0.777 | 5.107 | True | 0.610 | 0.244 | -15.007 | -13.284 | 2.377 | 12 | 0 | 0.024 | 1181.298 | 145 | 0 |
| l2p_nat_llm | 0 | 202 | -0.430 | 0.024 | 5.389 | True | 0.559 | 0.432 | -8.425 | -9.964 | 1.818 | 12 | 0 | 0.023 | 1164.322 | 114 | 0 |
| l12_llm | 0 | 7 | 0.000 | 0.097 | 4.901 | True | 0.366 | 0.366 | 0.000 | 0.000 | 0.000 | 31 | 0 | 0.007 | 339.772 | 59 | 0 |
| l12_llm | 0 | 11 | -0.002 | 0.126 | 4.546 | True | 0.540 | 0.539 | -0.008 | 0.012 | -0.005 | 31 | 0 | 0.006 | 295.382 | 104 | 0 |
| l12_llm | 0 | 23 | 0.076 | 0.176 | 4.502 | True | 0.412 | 0.418 | 0.979 | 1.018 | -0.151 | 64 | 0 | 0.014 | 1027.844 | 94 | 0 |
| l12_llm | 0 | 42 | -0.005 | 0.389 | 5.256 | True | 0.535 | 0.536 | -0.012 | -0.012 | 0.000 | 40 | 0 | 0.009 | 654.816 | 69 | 0 |
| l12_llm | 0 | 101 | 0.000 | 0.228 | 4.741 | True | 0.244 | 0.244 | 0.000 | 0.000 | 0.000 | 31 | 0 | 0.006 | 462.717 | 63 | 0 |
| l12_llm | 0 | 202 | 0.000 | 0.455 | 5.262 | True | 0.432 | 0.432 | 0.000 | 0.000 | 0.000 | 40 | 0 | 0.008 | 606.408 | 58 | 0 |
| l12_llm | 1 | 7 | 0.000 | 0.097 | 4.901 | True | 0.366 | 0.366 | 0.000 | 0.000 | 0.000 | 31 | 0 | 0.007 | 339.067 | 59 | 0 |
| l12_llm | 2 | 7 | 0.000 | 0.097 | 4.901 | True | 0.366 | 0.366 | 0.000 | 0.000 | 0.000 | 31 | 0 | 0.007 | 367.840 | 59 | 0 |

## LLM calls by leaf and outcome

| arm | rep | seed | L2P_plan:ok | L2P_repair:ok | default_reasons | L2P_repair:default | L1_value:ok | L2_shock:ok | L3_sibling:ok | L6_review:ok |
|---|---|---|---|---|---|---|---|---|---|---|
| l2p_aug_llm | 0 | 7 | 6.000 | 6.000 | {} | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| l2p_aug_llm | 0 | 11 | 6.000 | 6.000 | {} | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| l2p_aug_llm | 0 | 23 | 6.000 | 6.000 | {} | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| l2p_aug_llm | 0 | 42 | 6.000 | 6.000 | {} | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| l2p_aug_llm | 0 | 101 | 6.000 | 6.000 | {} | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| l2p_aug_llm | 0 | 202 | 6.000 | 5.000 | {'ValueError': 1} | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| l2p_nat_llm | 0 | 7 | 6.000 | 6.000 | {} | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| l2p_nat_llm | 0 | 11 | 6.000 | 6.000 | {} | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| l2p_nat_llm | 0 | 23 | 6.000 | 6.000 | {} | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| l2p_nat_llm | 0 | 42 | 6.000 | 5.000 | {'validation failed': 1} | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| l2p_nat_llm | 0 | 101 | 6.000 | 6.000 | {} | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| l2p_nat_llm | 0 | 202 | 6.000 | 6.000 | {} | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| l12_llm | 0 | 7 | 0.000 | 0.000 | {} | 0.000 | 2.000 | 4.000 | 24.000 | 1.000 |
| l12_llm | 0 | 11 | 0.000 | 0.000 | {} | 0.000 | 0.000 | 3.000 | 27.000 | 1.000 |
| l12_llm | 0 | 23 | 0.000 | 0.000 | {} | 0.000 | 6.000 | 10.000 | 46.000 | 2.000 |
| l12_llm | 0 | 42 | 0.000 | 0.000 | {} | 0.000 | 6.000 | 6.000 | 27.000 | 1.000 |
| l12_llm | 0 | 101 | 0.000 | 0.000 | {} | 0.000 | 1.000 | 8.000 | 21.000 | 1.000 |
| l12_llm | 0 | 202 | 0.000 | 0.000 | {} | 0.000 | 0.000 | 3.000 | 35.000 | 2.000 |
| l12_llm | 1 | 7 | 0.000 | 0.000 | {} | 0.000 | 2.000 | 4.000 | 24.000 | 1.000 |
| l12_llm | 2 | 7 | 0.000 | 0.000 | {} | 0.000 | 2.000 | 4.000 | 24.000 | 1.000 |

## L2′ run by run

| arm | rep | seed | run | shipped_from | fallback | intents | first_plan_intents | repair_intents | rejected | from_intents | l0_overridden | l0_held | allowance_used | allowance_total | shipped |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| l2p_aug_llm | 0 | 7 | 1 | compiler | None | 25 | 23.000 | 4.000 | 10 | 21 | 4 | 6 | 717.650 | 809.040 | 24 |
| l2p_aug_llm | 0 | 7 | 2 | compiler | None | 20 | 16.000 | 10.000 | 12 | 16 | 5 | 0 | 1261.670 | 1319.210 | 25 |
| l2p_aug_llm | 0 | 7 | 3 | compiler | None | 25 | 18.000 | 10.000 | 5 | 17 | 4 | 2 | 1169.780 | 1209.730 | 27 |
| l2p_aug_llm | 0 | 7 | 4 | compiler | None | 19 | 9.000 | 10.000 | 13 | 23 | 5 | 2 | 1835.090 | 2590.280 | 30 |
| l2p_aug_llm | 0 | 7 | 5 | compiler | None | 25 | 18.000 | 15.000 | 7 | 20 | 7 | 0 | 1484.940 | 2156.930 | 22 |
| l2p_aug_llm | 0 | 7 | 6 | compiler | None | 19 | 7.000 | 12.000 | 9 | 16 | 3 | 0 | 2230.030 | 14170.080 | 27 |
| l2p_aug_llm | 0 | 11 | 1 | compiler | None | 25 | 21.000 | 6.000 | 1 | 31 | 12 | 2 | 2089.640 | 3923.010 | 44 |
| l2p_aug_llm | 0 | 11 | 2 | compiler | None | 25 | 20.000 | 18.000 | 4 | 20 | 7 | 0 | 1365.710 | 1415.260 | 33 |
| l2p_aug_llm | 0 | 11 | 3 | compiler | None | 15 | 10.000 | 12.000 | 7 | 8 | 3 | 1 | 850.010 | 1141.360 | 20 |
| l2p_aug_llm | 0 | 11 | 4 | compiler | None | 25 | 22.000 | 16.000 | 7 | 16 | 0 | 0 | 1304.710 | 1888.480 | 28 |
| l2p_aug_llm | 0 | 11 | 5 | compiler | None | 25 | 18.000 | 17.000 | 12 | 24 | 1 | 4 | 1558.780 | 2634.750 | 26 |
| l2p_aug_llm | 0 | 11 | 6 | compiler | None | 17 | 10.000 | 10.000 | 9 | 31 | 10 | 0 | 1086.800 | 18876.710 | 35 |
| l2p_aug_llm | 0 | 23 | 1 | compiler | None | 25 | 13.000 | 14.000 | 5 | 14 | 9 | 0 | 403.370 | 672.180 | 26 |
| l2p_aug_llm | 0 | 23 | 2 | compiler | None | 25 | 23.000 | 14.000 | 3 | 20 | 6 | 0 | 790.510 | 990.260 | 30 |
| l2p_aug_llm | 0 | 23 | 3 | compiler | None | 23 | 25.000 | 8.000 | 6 | 16 | 4 | 0 | 1118.990 | 1129.810 | 26 |
| l2p_aug_llm | 0 | 23 | 4 | compiler | None | 10 | 5.000 | 8.000 | 1 | 8 | 2 | 0 | 902.570 | 1092.420 | 20 |
| l2p_aug_llm | 0 | 23 | 5 | compiler | None | 25 | 24.000 | 13.000 | 9 | 35 | 7 | 0 | 1581.810 | 1856.500 | 42 |
| l2p_aug_llm | 0 | 23 | 6 | compiler | None | 25 | 18.000 | 25.000 | 22 | 24 | 4 | 4 | 4934.090 | 11948.410 | 31 |
| l2p_aug_llm | 0 | 42 | 1 | compiler | None | 25 | 15.000 | 11.000 | 9 | 22 | 7 | 5 | 1175.140 | 1256.910 | 28 |
| l2p_aug_llm | 0 | 42 | 2 | compiler | None | 25 | 15.000 | 15.000 | 6 | 20 | 7 | 1 | 246.870 | 396.890 | 31 |
| l2p_aug_llm | 0 | 42 | 3 | compiler | None | 25 | 25.000 | 9.000 | 5 | 24 | 8 | 0 | 1305.090 | 1794.860 | 37 |
| l2p_aug_llm | 0 | 42 | 4 | compiler | None | 24 | 20.000 | 9.000 | 10 | 21 | 5 | 0 | 1215.610 | 1419.030 | 27 |
| l2p_aug_llm | 0 | 42 | 5 | compiler | None | 25 | 25.000 | 17.000 | 7 | 16 | 2 | 0 | 1578.630 | 1721.820 | 24 |
| l2p_aug_llm | 0 | 42 | 6 | compiler | None | 25 | 15.000 | 22.000 | 8 | 25 | 4 | 1 | 2821.070 | 10527.810 | 36 |
| l2p_aug_llm | 0 | 101 | 1 | compiler | None | 17 | 8.000 | 10.000 | 5 | 13 | 3 | 6 | 361.350 | 390.840 | 17 |
| l2p_aug_llm | 0 | 101 | 2 | compiler | None | 20 | 15.000 | 11.000 | 5 | 17 | 4 | 1 | 352.260 | 360.010 | 26 |
| l2p_aug_llm | 0 | 101 | 3 | compiler | None | 25 | 21.000 | 11.000 | 12 | 26 | 4 | 0 | 612.690 | 639.860 | 33 |
| l2p_aug_llm | 0 | 101 | 4 | compiler | None | 25 | 16.000 | 11.000 | 9 | 21 | 5 | 3 | 1288.730 | 1416.060 | 27 |
| l2p_aug_llm | 0 | 101 | 5 | compiler | None | 25 | 18.000 | 21.000 | 9 | 15 | 10 | 0 | 1425.640 | 1483.510 | 21 |
| l2p_aug_llm | 0 | 101 | 6 | compiler | None | 25 | 16.000 | 12.000 | 10 | 17 | 8 | 0 | 3232.940 | 10101.180 | 30 |
| l2p_aug_llm | 0 | 202 | 1 | compiler | None | 24 | 21.000 | 6.000 | 8 | 26 | 6 | 1 | 795.280 | 993.740 | 32 |
| l2p_aug_llm | 0 | 202 | 2 | compiler | None | 19 | 11.000 | 10.000 | 4 | 9 | 4 | 4 | 468.940 | 477.290 | 14 |
| l2p_aug_llm | 0 | 202 | 3 | compiler | None | 25 | 25.000 | 22.000 | 3 | 23 | 6 | 0 | 1302.220 | 1475.040 | 30 |
| l2p_aug_llm | 0 | 202 | 4 | compiler | None | 16 | 7.000 | 12.000 | 3 | 15 | 5 | 0 | 1331.340 | 1682.350 | 25 |
| l2p_aug_llm | 0 | 202 | 5 | compiler | None | 16 | 14.000 | 5.000 | 18 | 24 | 9 | 0 | 2295.640 | 2375.670 | 28 |
| l2p_aug_llm | 0 | 202 | 6 | compiler | None | 20 | nan | nan | 10 | 14 | 4 | 0 | 2685.070 | 11245.250 | 26 |
| l2p_nat_llm | 0 | 7 | 1 | compiler | None | 25 | 23.000 | 4.000 | 10 | 21 | 0 | 0 | 508.440 | 809.040 | 21 |
| l2p_nat_llm | 0 | 7 | 2 | compiler | None | 25 | 13.000 | 13.000 | 7 | 19 | 0 | 0 | 883.950 | 963.380 | 19 |
| l2p_nat_llm | 0 | 7 | 3 | compiler | None | 21 | 11.000 | 13.000 | 11 | 21 | 0 | 0 | 1479.690 | 1630.740 | 21 |
| l2p_nat_llm | 0 | 7 | 4 | compiler | None | 25 | 11.000 | 18.000 | 4 | 21 | 0 | 0 | 1089.330 | 1339.360 | 21 |
| l2p_nat_llm | 0 | 7 | 5 | compiler | None | 25 | 15.000 | 14.000 | 6 | 23 | 0 | 0 | 1819.950 | 1956.660 | 23 |
| l2p_nat_llm | 0 | 7 | 6 | compiler | None | 23 | 14.000 | 13.000 | 7 | 21 | 0 | 0 | 1713.110 | 10442.170 | 21 |
| l2p_nat_llm | 0 | 11 | 1 | compiler | None | 25 | 21.000 | 6.000 | 1 | 31 | 0 | 0 | 1296.160 | 3923.010 | 31 |
| l2p_nat_llm | 0 | 11 | 2 | compiler | None | 15 | 11.000 | 8.000 | 5 | 13 | 0 | 0 | 326.760 | 327.430 | 13 |
| l2p_nat_llm | 0 | 11 | 3 | compiler | None | 19 | 15.000 | 6.000 | 8 | 27 | 0 | 0 | 1025.520 | 1273.270 | 27 |
| l2p_nat_llm | 0 | 11 | 4 | compiler | None | 25 | 18.000 | 13.000 | 4 | 29 | 0 | 0 | 2293.140 | 3011.300 | 29 |
| l2p_nat_llm | 0 | 11 | 5 | compiler | None | 22 | 17.000 | 11.000 | 11 | 18 | 0 | 0 | 724.550 | 1860.350 | 18 |
| l2p_nat_llm | 0 | 11 | 6 | compiler | None | 22 | 12.000 | 11.000 | 6 | 23 | 0 | 0 | 1241.610 | 12243.920 | 23 |
| l2p_nat_llm | 0 | 23 | 1 | compiler | None | 24 | 5.000 | 20.000 | 6 | 23 | 0 | 0 | 644.070 | 879.830 | 23 |
| l2p_nat_llm | 0 | 23 | 2 | compiler | None | 25 | 19.000 | 22.000 | 6 | 19 | 0 | 0 | 873.680 | 3889.030 | 19 |
| l2p_nat_llm | 0 | 23 | 3 | compiler | None | 25 | 19.000 | 12.000 | 3 | 22 | 0 | 0 | 1520.480 | 1641.540 | 22 |
| l2p_nat_llm | 0 | 23 | 4 | compiler | None | 24 | 19.000 | 10.000 | 7 | 19 | 0 | 0 | 700.950 | 863.420 | 19 |
| l2p_nat_llm | 0 | 23 | 5 | compiler | None | 25 | 22.000 | 14.000 | 2 | 21 | 0 | 0 | 1051.140 | 1275.550 | 21 |
| l2p_nat_llm | 0 | 23 | 6 | compiler | None | 25 | 21.000 | 13.000 | 5 | 16 | 0 | 0 | 1127.730 | 8400.950 | 16 |
| l2p_nat_llm | 0 | 42 | 1 | compiler | None | 22 | 16.000 | 11.000 | 6 | 23 | 0 | 0 | 362.010 | 388.920 | 23 |
| l2p_nat_llm | 0 | 42 | 2 | compiler | None | 25 | 18.000 | 25.000 | 8 | 25 | 0 | 0 | 720.630 | 961.210 | 25 |
| l2p_nat_llm | 0 | 42 | 3 | compiler | None | 21 | 13.000 | 14.000 | 5 | 18 | 0 | 0 | 718.730 | 732.200 | 18 |
| l2p_nat_llm | 0 | 42 | 4 | compiler | None | 25 | 9.000 | 21.000 | 10 | 19 | 0 | 0 | 1272.470 | 1350.540 | 19 |
| l2p_nat_llm | 0 | 42 | 5 | compiler | None | 24 | 11.000 | 15.000 | 22 | 13 | 0 | 0 | 998.470 | 1008.060 | 13 |
| l2p_nat_llm | 0 | 42 | 6 | compiler | None | 18 | nan | nan | 9 | 32 | 0 | 0 | 2283.490 | 6301.970 | 32 |
| l2p_nat_llm | 0 | 101 | 1 | compiler | None | 25 | 24.000 | 16.000 | 5 | 27 | 0 | 0 | 641.450 | 731.960 | 27 |
| l2p_nat_llm | 0 | 101 | 2 | compiler | None | 22 | 14.000 | 11.000 | 12 | 16 | 0 | 0 | 562.830 | 669.620 | 16 |
| l2p_nat_llm | 0 | 101 | 3 | compiler | None | 25 | 23.000 | 11.000 | 8 | 32 | 0 | 0 | 2104.080 | 2143.590 | 24 |
| l2p_nat_llm | 0 | 101 | 4 | compiler | None | 25 | 25.000 | 19.000 | 2 | 26 | 0 | 0 | 1478.400 | 1480.200 | 26 |
| l2p_nat_llm | 0 | 101 | 5 | compiler | None | 23 | 18.000 | 11.000 | 10 | 39 | 0 | 0 | 1563.040 | 3452.130 | 39 |
| l2p_nat_llm | 0 | 101 | 6 | compiler | None | 25 | 22.000 | 22.000 | 9 | 13 | 0 | 0 | 339.400 | 9014.470 | 13 |
| l2p_nat_llm | 0 | 202 | 1 | compiler | None | 21 | 15.000 | 10.000 | 6 | 15 | 0 | 0 | 1313.180 | 1499.550 | 15 |
| l2p_nat_llm | 0 | 202 | 2 | compiler | None | 20 | 9.000 | 15.000 | 6 | 17 | 0 | 0 | 368.080 | 420.470 | 17 |
| l2p_nat_llm | 0 | 202 | 3 | compiler | None | 25 | 20.000 | 19.000 | 12 | 35 | 0 | 0 | 1046.690 | 1094.970 | 35 |
| l2p_nat_llm | 0 | 202 | 4 | compiler | None | 25 | 15.000 | 21.000 | 7 | 20 | 0 | 0 | 1174.950 | 1179.380 | 20 |
| l2p_nat_llm | 0 | 202 | 5 | compiler | None | 25 | 15.000 | 17.000 | 5 | 15 | 0 | 0 | 740.270 | 1305.280 | 15 |
| l2p_nat_llm | 0 | 202 | 6 | compiler | None | 19 | 16.000 | 8.000 | 6 | 12 | 0 | 0 | 61.180 | 7281.650 | 12 |

## L2′ intent verbs (total)

- `l2p_aug_llm`: {'lead_market': 274, 'hold': 46, 'raise_bid': 162, 'raise_budget': 93, 'cut_budget': 103, 'yield_market': 109, 'cut_bid': 17}
- `l2p_nat_llm`: {'lead_market': 310, 'hold': 24, 'raise_bid': 158, 'raise_budget': 102, 'cut_budget': 115, 'yield_market': 103, 'cut_bid': 23}

## L2′ plan notes and top rejections, per run

- `l2p_aug_llm` r0 seed 7 run 1: Focused spend on S4 scale campaigns with highest iroas (>5.5) and positive reach trends, using target_slot 5 to bypass the 80% raise cap. Corrected HYD branded search wrong-holder to maximize incremental value while stay  
  rejections: {'no predicted gain from this raise': 7, 'G: already at slot  on >= % of impressions': 2, 'over allowance': 1}  
  actions: {'increase_cpm': 5, 'reduce_cpm': 19}
- `l2p_aug_llm` r0 seed 7 run 2: Prioritized scale role funding through targeted budget reallocation from hold/trim portfolios. Corrected four misplaced market leaders to boost true incremental revenue. Paused zero-OSA anomaly to prevent wasted spend an  
  rejections: {'unknown campaign': 6, 'no predicted gain from this raise': 5, 'leader S cannot take slot': 1}  
  actions: {'increase_cpm': 3, 'increase_budget': 1, 'reduce_cpm': 18, 'reduce_budget': 3}
- `l2p_aug_llm` r0 seed 7 run 3: Focused on funding efficient 'fund' campaigns and activating bid room on 'scale' cells with verified incrementality. Corrected three wrong-holder contested markets to push volume to highest incremental SKUs. Held weak tr  
  rejections: {'no predicted gain from this raise': 4, 'over allowance': 1}  
  actions: {'increase_cpm': 6, 'increase_budget': 1, 'reduce_cpm': 16, 'reduce_budget': 4}
- `l2p_aug_llm` r0 seed 7 run 4: Removed previously rejected saturated-blr generic raise. Focused budget/headroom on validated scale roles (S2-DEL, S1-PUN, S2-PUN, S4-HYD) while cutting persistently weak Kids Soap spend to protect the 4.63 roas floor. E  
  rejections: {'no predicted gain from this raise': 7, 'G: already at slot  on >= % of impressions': 5, 'no budget change possible': 1}  
  actions: {'increase_budget': 5, 'increase_cpm': 7, 'reduce_cpm': 16, 'reduce_budget': 2}
- `l2p_aug_llm` r0 seed 7 run 5: Prioritized funding for fund SKUs running dry and targeted bid lifts on scale cells with proven mroas uplift. Removed previously rejected budget/bid actions on saturated slots and adjusted lead_market targets to exclude   
  rejections: {'no predicted gain from this raise': 6, 'G: cell misses goal': 1}  
  actions: {'increase_cpm': 4, 'increase_budget': 4, 'reduce_cpm': 11, 'reduce_budget': 3}
- `l2p_aug_llm` r0 seed 7 run 6: Revised plan drops previously rejected brand-lead intents in favor of targeted generic bid-ups and budget reallocations toward scale-tier SKUs. Contested markets on generic K05 shifted to S4 where incremental scores are   
  rejections: {'G: ran out on fewer than  of the last  days': 5, 'no predicted gain from this raise': 4}  
  actions: {'increase_cpm': 4, 'increase_budget': 5, 'reduce_budget': 2, 'reduce_cpm': 16}
- `l2p_aug_llm` r0 seed 11 run 1: Shifted budget from low-incrementality Trim soap to high-iota Fund/Scale body wash and shower gel cells. Relieved chronic caps on efficient SKUs while using freed allowance to capture incremental volume. Contested market  
  rejections: {'no predicted gain from this raise': 1}  
  actions: {'increase_cpm': 9, 'increase_budget': 4, 'reduce_cpm': 25, 'reduce_budget': 6}
- `l2p_aug_llm` r0 seed 11 run 2: Focused purely on raising budget for fully-funded campaigns and bidding up efficiently clearing generic cells across S2 and S4 portfolios. Avoided contested leader changes and blocked cells from prior run. Headroom suppo  
  rejections: {'over allowance': 2, 'no predicted gain from this raise': 2}  
  actions: {'increase_cpm': 7, 'increase_budget': 3, 'reduce_cpm': 23}
- `l2p_aug_llm` r0 seed 11 run 3: Prioritized scaling high-iROAS SKUs (S1, S2, S4) on CLEARS generic and brand keywords while resolving budget bottlenecks in fund roles. Dropped rejected S3/S5 budget cuts and lead attempts on MISSES cells to maintain com  
  rejections: {'no predicted gain from this raise': 5, 'G: already at slot  on >= % of impressions': 2}  
  actions: {'increase_budget': 3, 'increase_cpm': 2, 'reduce_cpm': 15}
- `l2p_aug_llm` r0 seed 11 run 4: Respects G4 OSA block for S2-HYD (0.42) by avoiding bid increases there and using only yield mechanisms. Aligns four contested markets by shifting leadership to highest-IOTA SKUs. Cuts lean/trim portfolios (S1-BLR, S3-DE  
  rejections: {'no predicted gain from this raise': 7}  
  actions: {'increase_cpm': 1, 'increase_budget': 3, 'reduce_cpm': 24}
- `l2p_aug_llm` r0 seed 11 run 5: Focused bid raises on high-iRoAS generic cells in Scale campaigns to maximize incremental volume through run 6. Resolved contested market misallocations via precise lead/yield moves, explicitly yielding S1 on DEL:K04 to   
  rejections: {'G: already at slot  on >= % of impressions': 6, 'no predicted gain from this raise': 6}  
  actions: {'increase_cpm': 8, 'increase_budget': 1, 'reduce_cpm': 17}
- `l2p_aug_llm` r0 seed 11 run 6: Dropped previously rejected intents (overlapping leads, slot-capped bids, zero-gain markets). Concentrated bid lifts on high-iota generic cells with proven scale roles and confirmed slot headroom (<80%). Corrected two mi  
  rejections: {'no predicted gain from this raise': 8, 'G: already at slot  on >= % of impressions': 1}  
  actions: {'increase_cpm': 3, 'increase_budget': 1, 'reduce_cpm': 31}
- `l2p_aug_llm` r0 seed 23 run 1: Reallocated ₹~900+/day from inefficient Hold/Fund campaigns to Scale campaigns to expand incremental offtake while staying within the ₹300 allowance via strategic cuts. Corrected market leadership across BLR, DEL, and MU  
  rejections: {'G: ran out on fewer than  of the last  days': 3, 'over allowance': 1, 'no predicted gain from this raise': 1}  
  actions: {'increase_cpm': 4, 'increase_budget': 1, 'reduce_cpm': 18, 'reduce_budget': 3}
- `l2p_aug_llm` r0 seed 23 run 2: Corrected slot leadership across 5 contested markets where wrong holders were draining incremental efficiency. Adjusted budgets to fund high-velocity performers while trimming weak holds, staying within allowance and avo  
  rejections: {'no predicted gain from this raise': 2, 'leader S cannot take slot': 1}  
  actions: {'increase_cpm': 5, 'increase_budget': 1, 'reduce_cpm': 21, 'reduce_budget': 3}
- `l2p_aug_llm` r0 seed 23 run 3: Reallocated allowance toward proven scale markets (S2 generic, S3 PUN) and fully incremental competition share (S4 DEL competition) while trimming inefficient S1-MUM spend. Bid adjustments respect slot-share guardrails a  
  rejections: {'over allowance': 3, 'no predicted gain from this raise': 3}  
  actions: {'increase_budget': 2, 'increase_cpm': 2, 'reduce_cpm': 19, 'reduce_budget': 3}
- `l2p_aug_llm` r0 seed 23 run 4: Previous budget raises for C-S2-DEL, C-S2-BLR, and C-S3-BLR were dropped due to insufficient run-out days (G5 rule). Execution pivots to correcting misplaced contested-market leadership and lifting bids on cleared generi  
  rejections: {'no predicted gain from this raise': 1}  
  actions: {'increase_cpm': 5, 'increase_budget': 1, 'reduce_cpm': 14}
- `l2p_aug_llm` r0 seed 23 run 5: Shifted aggression to cleared, high-iota cells with slot-1 share below 80% to satisfy G3 guardrails while avoiding previously rejected MISSES/THIN targets. Preserved budget by halting low-ROI holds/trims and defending S3  
  rejections: {'no predicted gain from this raise': 8, 'over allowance': 1}  
  actions: {'increase_cpm': 11, 'reduce_cpm': 31}
- `l2p_aug_llm` r0 seed 23 run 6: Resolved all 12 flagged wrong-holder contests to route impressions to the highest incremental SKU. Directed remaining headroom into S2/S4 cells with clear slot capacity and strong iroas, avoiding previously rejected satu  
  rejections: {'G: already at slot  on >= % of impressions': 12, 'no predicted gain from this raise': 7, 'leader S cannot take slot': 3}  
  actions: {'increase_cpm': 14, 'increase_budget': 7, 'reduce_cpm': 10}
- `l2p_aug_llm` r0 seed 42 run 1: Prioritizes correcting wrong-holder market contest mismatches to reallocate impression costs to higher-incrementality SKUs, supplementing with targeted bid raises on the most efficient generic cells with available positi  
  rejections: {'G: already at slot  on >= % of impressions': 5, 'no predicted gain from this raise': 3, 'over allowance': 1}  
  actions: {'increase_cpm': 9, 'reduce_cpm': 19}
- `l2p_aug_llm` r0 seed 42 run 2: Focused cuts on low-iota Soap SKUs (S1, S3) across metros to free ample allowance. Redirected savings to fund budgets for out-of-stock-prone Body Wash campaigns (S2) and bid up high-incrementality generic/competition cel  
  rejections: {'no predicted gain from this raise': 4, 'over allowance': 2}  
  actions: {'increase_budget': 2, 'increase_cpm': 1, 'reduce_cpm': 19, 'reduce_budget': 9}
- `l2p_aug_llm` r0 seed 42 run 3: Dropped previously rejected intents due to blocked slots (≥80%), MISSES verdicts, and insufficient run-out days for budget raises. Shifted spend from underperforming hold/trim Soap campaigns (DEL, BLR, HYD) to high-iROAS  
  rejections: {'no predicted gain from this raise': 5}  
  actions: {'increase_cpm': 4, 'increase_budget': 5, 'reduce_cpm': 23, 'reduce_budget': 5}
- `l2p_aug_llm` r0 seed 42 run 4: Prioritize high-iROAS segments (Body Wash, Shower Gel) with targeted lead_market and bid raises where slot-share headroom exists. Freeze S2-HYD and low-efficiency Kids Soap spends to protect portfolio ROAS floor and comp  
  rejections: {'no predicted gain from this raise': 6, 'G: already at slot  on >= % of impressions': 3, 'over allowance': 1}  
  actions: {'increase_budget': 1, 'increase_cpm': 6, 'reduce_cpm': 14, 'reduce_budget': 6}
- `l2p_aug_llm` r0 seed 42 run 5: Corrected misallocated market leadership across six contested city-keyword markets to prioritize highest incremental SKUs. Cut three underperforming Soap holdings to protect the ROAS floor, redirecting funds to scale-rea  
  rejections: {'no predicted gain from this raise': 7}  
  actions: {'increase_cpm': 3, 'increase_budget': 2, 'reduce_cpm': 15, 'reduce_budget': 4}
- `l2p_aug_llm` r0 seed 42 run 6: Fixed previous rejections by replacing ineffective raise_bids on brand/competitor cells with lead_market directives for contested markets where wrong holders existed. Added targeted bid increases only on high-incremental  
  rejections: {'no predicted gain from this raise': 7, 'leader S cannot take slot': 1}  
  actions: {'increase_cpm': 7, 'increase_budget': 6, 'reduce_cpm': 23}
- `l2p_aug_llm` r0 seed 101 run 1: Dropped S3 leadership bids that triggered MISSES/blockers. Reduced raise count and applied holds to Trim campaigns to conserve the ₹300/day allowance while pushing high-iroas mROAS cells. Portfolio ROAS floor protected.  
  rejections: {'over allowance': 3, 'no predicted gain from this raise': 2}  
  actions: {'increase_cpm': 3, 'reduce_budget': 4, 'reduce_cpm': 10}
- `l2p_aug_llm` r0 seed 101 run 2: Net budget delta is +₹10/day, keeping total change well within the ₹300 allowance while stabilizing two run-out funds. Bid increases target scalable cells below the 80% slot-1 threshold to avoid hard blocks. Market lead   
  rejections: {'over allowance': 3, 'no predicted gain from this raise': 2}  
  actions: {'increase_budget': 2, 'increase_cpm': 1, 'reduce_cpm': 16, 'reduce_budget': 7}
- `l2p_aug_llm` r0 seed 101 run 3: Replaced rejected leads/budget bumps on MISSES or under-runout campaigns with targeted bid expansions on CLEARING cells below the 80% slot threshold and two qualified budget unlocks. Added market-leadership corrections w  
  rejections: {'no predicted gain from this raise': 6, 'unknown campaign': 3, 'over allowance': 3}  
  actions: {'increase_cpm': 5, 'reduce_cpm': 23, 'reduce_budget': 5}
- `l2p_aug_llm` r0 seed 101 run 4: Plan pivots from previously rejected brand-keyword leads to high-incrementality generic/competition opportunities and targeted budget boosts on consistently out-of-stock funded campaigns. Maintains strict adherence to OS  
  rejections: {'no predicted gain from this raise': 5, 'G: already at slot  on >= % of impressions': 4}  
  actions: {'increase_budget': 5, 'increase_cpm': 5, 'reduce_budget': 3, 'reduce_cpm': 14}
- `l2p_aug_llm` r0 seed 101 run 5: Removed previously rejected intents caused by slot saturation or zero predicted gain. Focused remaining allowance on high-mroas generic cells and resolved internal contest misallocations where S2/S4 swapped leadership ba  
  rejections: {'no predicted gain from this raise': 5, 'over allowance': 3, 'G: already at slot  on >= % of impressions': 1}  
  actions: {'increase_budget': 3, 'increase_cpm': 6, 'reduce_budget': 3, 'reduce_cpm': 9}
- `l2p_aug_llm` r0 seed 101 run 6: Plan shifts spend from capping inefficient holds/trims to funding 5 frequent run-outs and raising bids on 5 scale cells with >56% slot headroom and CLEARS verdicts. Two lead_market actions correct misplaced ownership in   
  rejections: {'no predicted gain from this raise': 6, 'G: already at slot  on >= % of impressions': 4}  
  actions: {'increase_budget': 8, 'increase_cpm': 8, 'reduce_cpm': 11, 'reduce_budget': 3}
- `l2p_aug_llm` r0 seed 202 run 1: Dropped all previously rejected leads and budget raises due to failed goals, insufficient run-outs, or lack of allowance. Focused execution on high-incrementality brand keyword raises where slot share is low, alongside t  
  rejections: {'no predicted gain from this raise': 7, 'over allowance': 1}  
  actions: {'increase_cpm': 6, 'increase_budget': 1, 'reduce_budget': 4, 'reduce_cpm': 21}
- `l2p_aug_llm` r0 seed 202 run 2: Allocated budget room to top-performing fund campaigns while freezing inefficient SKUs to safeguard the ROAS floor. Targeted bid increases only on verified efficient cells with adequate inventory and slot headroom, and r  
  rejections: {'over allowance': 2, 'leader S cannot take slot': 1, 'no predicted gain from this raise': 1}  
  actions: {'increase_cpm': 2, 'increase_budget': 2, 'reduce_cpm': 9, 'reduce_budget': 1}
- `l2p_aug_llm` r0 seed 202 run 3: Prioritized fund/scale campaigns within allowance using small budget raises and targeted bid lifts on high-mroas/iota cells. Avoided S5 leads per G7 constraint. Trimmed hold/weak budgets to free room and protect portfoli  
  rejections: {'no predicted gain from this raise': 3}  
  actions: {'increase_budget': 4, 'increase_cpm': 5, 'reduce_cpm': 16, 'reduce_budget': 5}
- `l2p_aug_llm` r0 seed 202 run 4: Prioritize budget raises on fully run-out fund campaigns (S2-DEL, S1-HYD) to capture efficient volume while trimming S3 and S5 to safeguard the ROAS floor. Resolve top contested markets for S5 and S3 to lift incremental   
  rejections: {'no predicted gain from this raise': 2, 'leader S cannot take slot': 1}  
  actions: {'increase_cpm': 2, 'increase_budget': 3, 'reduce_cpm': 14, 'reduce_budget': 6}
- `l2p_aug_llm` r0 seed 202 run 5: Removed previously flagged market leads and saturated-cell raises. Shifts spend from low-incrementality S1 brand bids to high-iRoAS S4/S2 generic pools, while topping up the heavily out-spent S2-DEL fund budget to secure  
  rejections: {'G: already at slot  on >= % of impressions': 10, 'over allowance': 5, 'no predicted gain from this raise': 3}  
  actions: {'increase_cpm': 8, 'increase_budget': 1, 'reduce_cpm': 17, 'reduce_budget': 2}
- `l2p_aug_llm` r0 seed 202 run 6: Prioritized correcting contested market misallocations by directing slot-1 leadership to SKUs with demonstrably higher incremental revenue per impression, particularly elevating efficient Scales/Saturates over Trims/Hold  
  rejections: {'no predicted gain from this raise': 5, 'leader S cannot take slot': 3, 'G: already at slot  on >= % of impressions': 2}  
  actions: {'increase_cpm': 8, 'increase_budget': 5, 'reduce_cpm': 13}
- `l2p_nat_llm` r0 seed 7 run 1: Focused spend on S4 scale campaigns with highest iroas (>5.5) and positive reach trends, using target_slot 5 to bypass the 80% raise cap. Corrected HYD branded search wrong-holder to maximize incremental value while stay  
  rejections: {'no predicted gain from this raise': 7, 'G: already at slot  on >= % of impressions': 2, 'over allowance': 1}  
  actions: {'increase_cpm': 4, 'reduce_cpm': 17}
- `l2p_nat_llm` r0 seed 7 run 2: Bid increases target high-mroas cells safely below the 80% slot-1 guardrail and OSA floor. Contested market realignments displace lower-IOTA siblings to maximize incremental revenue without breaching the ₹300 daily allow  
  rejections: {'over allowance': 3, 'no predicted gain from this raise': 3, 'leader S cannot take slot': 1}  
  actions: {'increase_cpm': 4, 'increase_budget': 2, 'reduce_cpm': 11, 'reduce_budget': 2}
- `l2p_nat_llm` r0 seed 7 run 3: Budget shifts prioritize high-iROAS Shower Gel (S4) campaigns while cutting low-efficiency Kids Soap (S5) and weak Soap (S3) exposure. Contestated markets with wrong holders are corrected via lead_market to align slot 1   
  rejections: {'G: already at slot  on >= % of impressions': 5, 'no predicted gain from this raise': 5, 'over allowance': 1}  
  actions: {'increase_cpm': 7, 'increase_budget': 1, 'reduce_cpm': 11, 'reduce_budget': 2}
- `l2p_nat_llm` r0 seed 7 run 4: Pivoted budget from OSA-constrained S2-HYD and trim tiers (S3/S5) to high-frequency run-out scales/funds (S2/S4/S1). Replaced risky specific-keyword scopes with campaign-level budget adjustments to guarantee compiler acc  
  rejections: {'G: ran out on fewer than  of the last  days': 3, 'no predicted gain from this raise': 1}  
  actions: {'increase_budget': 5, 'increase_cpm': 2, 'reduce_budget': 11, 'reduce_cpm': 3}
- `l2p_nat_llm` r0 seed 7 run 5: Shifted focus to high mroas generic keywords with healthy slot dispersion to secure predictable incrementality, while funding run-outs for efficient fund/scale SKUs and pruning low-value trim budgets to stay within the 1  
  rejections: {'no predicted gain from this raise': 4, 'scope matches no active cell': 1, 'no budget change possible': 1}  
  actions: {'increase_budget': 3, 'increase_cpm': 9, 'reduce_cpm': 8, 'reduce_budget': 3}
- `l2p_nat_llm` r0 seed 7 run 6: Focused on replenishing heavily constrained funds and scaling efficient bid cells with ample slot-1 headroom. Corrected key contested markets to align with incremental ROI leaders. Avoided saturated cells and MISSES verd  
  rejections: {'no predicted gain from this raise': 7}  
  actions: {'increase_cpm': 5, 'increase_budget': 4, 'reduce_cpm': 12}
- `l2p_nat_llm` r0 seed 11 run 1: Shifted budget from low-incrementality Trim soap to high-iota Fund/Scale body wash and shower gel cells. Relieved chronic caps on efficient SKUs while using freed allowance to capture incremental volume. Contested market  
  rejections: {'no predicted gain from this raise': 1}  
  actions: {'increase_cpm': 8, 'increase_budget': 1, 'reduce_cpm': 16, 'reduce_budget': 6}
- `l2p_nat_llm` r0 seed 11 run 2: Replaced rejected leads on MISSES cells and overspent budget raises with targeted budget releases for funded SKUs, safe bid lifts on CLEARS generic cells, and high-ROI market share shifts. Maintains portfolio iROAS floor  
  rejections: {'G: already at slot  on >= % of impressions': 2, 'no predicted gain from this raise': 2, 'over allowance': 1}  
  actions: {'increase_cpm': 2, 'increase_budget': 2, 'reduce_cpm': 9}
- `l2p_nat_llm` r0 seed 11 run 3: Plan shifts budget and bids from trimmed/low-iota segments to scale campaigns and high-mroas generic cells. Contested market leaders adjusted only where cells CLEAR G7 guardrails, avoiding prior slot-1 failures. Budget c  
  rejections: {'no predicted gain from this raise': 4, 'unknown campaign': 3, 'unknown city BLR,DEL,HYD,MUM': 1}  
  actions: {'increase_budget': 5, 'increase_cpm': 2, 'reduce_budget': 10, 'reduce_cpm': 10}
- `l2p_nat_llm` r0 seed 11 run 4: Dropped all previously rejected intents due to G4 (S2-HYD OSA < 60%), G7 (cell misses goal), G3 (>=80% slot-1), or flat predictions. Shifted focus to K05 generic keywords across scale/fund campaigns where mroas_up20 is p  
  rejections: {'no predicted gain from this raise': 4}  
  actions: {'increase_budget': 5, 'increase_cpm': 6, 'reduce_cpm': 18}
- `l2p_nat_llm` r0 seed 11 run 5: Focused plan for run 5 corrects prior misallocations by redirecting leadership to highest-incrementality SKUs in contested generic keywords and raising bids only on cleared cells with verified headroom (<80% slot share).  
  rejections: {'no predicted gain from this raise': 6, 'G: already at slot  on >= % of impressions': 4, 'no budget change possible': 1}  
  actions: {'increase_cpm': 4, 'reduce_cpm': 13, 'reduce_budget': 1}
- `l2p_nat_llm` r0 seed 11 run 6: Allocates remaining runheadroom to fund replenishment and high-iota generic raises for Scale/Fund portfolios. Corrects 6 misplaced market holders across key metros to capture incremental share efficiently while holding t  
  rejections: {'no predicted gain from this raise': 6}  
  actions: {'increase_cpm': 4, 'increase_budget': 3, 'reduce_cpm': 14, 'reduce_budget': 2}
- `l2p_nat_llm` r0 seed 23 run 1: Reallocation strategy uses market yields and targeted bid lifts to shift share from inefficient body wash and kids soap pockets toward high-incrementality shower gel and soap generics. Budget cuts and holds on trim/hold   
  rejections: {'G: already at slot  on >= % of impressions': 3, 'no predicted gain from this raise': 2, 'over allowance': 1}  
  actions: {'increase_cpm': 6, 'reduce_cpm': 12, 'reduce_budget': 5}
- `l2p_nat_llm` r0 seed 23 run 2: Corrected contested market holders to align with highest incremental score per M-ref data. Used small budget raises across four fund campaigns to stay within the ₹300 daily allowance while relieving hard caps. Raised bid  
  rejections: {'leader S cannot take slot': 4, 'no predicted gain from this raise': 2}  
  actions: {'increase_cpm': 4, 'reduce_cpm': 15}
- `l2p_nat_llm` r0 seed 23 run 3: Prioritized efficient scales (S2-HYD, S2-DEL) and structural market corrections (S4→S2 leadership) to maximize incremental offtake. Pruned exhausted holds to preserve daily allowance for high-ROI raises.  
  rejections: {'G: already at slot  on >= % of impressions': 2, 'no predicted gain from this raise': 1}  
  actions: {'increase_budget': 4, 'increase_cpm': 6, 'reduce_cpm': 10, 'reduce_budget': 2}
- `l2p_nat_llm` r0 seed 23 run 4: Removed all previously rejected intents. Realized contested market leadership to SKUs with highest incremental scores (S2, S3, S4) to maximize portfolio iROAS. Directed targeted bid increases only on efficient, non-satur  
  rejections: {'no predicted gain from this raise': 5, 'leader S cannot take slot': 1, 'over allowance': 1}  
  actions: {'increase_cpm': 4, 'reduce_budget': 4, 'reduce_cpm': 11}
- `l2p_nat_llm` r0 seed 23 run 5: Prioritizes scaling efficient scale-role SKUs on generic/competition keywords with open bid headroom and <80% slot-1 share. Yields inefficient holders in contested markets to redirect traffic to higher-iOTA competitors.   
  rejections: {'no predicted gain from this raise': 2}  
  actions: {'increase_cpm': 8, 'reduce_budget': 9, 'reduce_cpm': 4}
- `l2p_nat_llm` r0 seed 23 run 6: Replaced rejected market leads with targeted budget unsealing for exhausted fund/hold campaigns and corrected ownership across 9 contested markets where incumbent holders were demonstrably weaker. Bid adjustments kept mi  
  rejections: {'no predicted gain from this raise': 3, 'leader S cannot take slot': 2}  
  actions: {'increase_cpm': 6, 'increase_budget': 3, 'reduce_cpm': 7}
- `l2p_nat_llm` r0 seed 42 run 1: Aggressively cut low-performing trim budgets (S1-MUM, S1-BLR) to generate sufficient allowance headroom (~₹2000 freed). Redirected this liquidity into lead_market actions that shift keyword share to high-iroas S4 and S2   
  rejections: {'over allowance': 4, 'no predicted gain from this raise': 2}  
  actions: {'increase_cpm': 5, 'reduce_budget': 5, 'reduce_cpm': 13}
- `l2p_nat_llm` r0 seed 42 run 2: Corrected market leadership across all flagged wrong-holder contests to prioritize the highest-incremental SKUs. Raised bids only on scale-role generic cells with proven headroom and positive predicted lift, while trimmi  
  rejections: {'no predicted gain from this raise': 6, 'leader S cannot take slot': 2}  
  actions: {'increase_cpm': 5, 'reduce_cpm': 20}
- `l2p_nat_llm` r0 seed 42 run 3: Prioritized correcting misallocated contest markets (wrong_holder=True) by yielding from inefficient incumbents and leading with higher-iota SKUs. Avoided forcing leads on MISSES-verdict cells to prevent G7 compliance fa  
  rejections: {'no predicted gain from this raise': 4, 'over allowance': 1}  
  actions: {'increase_cpm': 3, 'reduce_cpm': 15}
- `l2p_nat_llm` r0 seed 42 run 4: Dropped INT-R3 and INT-R4 due to G3 guardrail (≥80% slot-1 share blocks raises); dropped INT-L2 due to lack of predicted gain and THIN verdict. Plan shifts K05 generic leadership to S2 (Body Wash) in BLR/DEL/HYD/PUN wher  
  rejections: {'over allowance': 4, 'no predicted gain from this raise': 3, 'G: already at slot  on >= % of impressions': 2}  
  actions: {'increase_cpm': 2, 'increase_budget': 2, 'reduce_cpm': 9, 'reduce_budget': 6}
- `l2p_nat_llm` r0 seed 42 run 5: Resolved four incorrect market holders identified in the brief by swapping lead/yield rights to higher-incrementality SKUs. Directed bid increases exclusively to generic keywords with sub-80% slot penetration and demonst  
  rejections: {'unknown campaign': 7, 'G: already at slot  on >= % of impressions': 6, 'no predicted gain from this raise': 6}  
  actions: {'increase_cpm': 4, 'increase_budget': 1, 'reduce_cpm': 8}
- `l2p_nat_llm` r0 seed 42 run 6: Shift leadership in contested markets to high-iRoAS Body Wash SKUs to maximize incremental value. Unblocking budgets for funded campaigns while cutting weak trim/hold portfolios improves overall ROAS headroom and protect  
  rejections: {'G: already at slot  on >= % of impressions': 5, 'no predicted gain from this raise': 4}  
  actions: {'increase_cpm': 10, 'increase_budget': 4, 'reduce_budget': 10, 'reduce_cpm': 8}
- `l2p_nat_llm` r0 seed 101 run 1: Plan defends the ROAS floor by cutting low-iota trim/hold SKUs (S1, S5) and reallocating allowance to efficient Scale/Fund campaigns (S4, S2, S3) via targeted bid raises on high mroas_up20 generic cells. Yield intents co  
  rejections: {'no predicted gain from this raise': 4, 'over allowance': 1}  
  actions: {'increase_budget': 5, 'increase_cpm': 2, 'reduce_budget': 8, 'reduce_cpm': 12}
- `l2p_nat_llm` r0 seed 101 run 2: Prioritized high-iota generic keywords in scale/fund roles while strictly respecting slot-1 occupancy and allowance guardrails. Resolved four contest misallocations by yielding lower-marginal Shower Gel SKUs to higher-ma  
  rejections: {'over allowance': 8, 'no predicted gain from this raise': 3, 'G: already at slot  on >= % of impressions': 1}  
  actions: {'increase_budget': 5, 'increase_cpm': 1, 'reduce_cpm': 10}
- `l2p_nat_llm` r0 seed 101 run 3: Prioritized budget relief for exhausted fund cities and aggressive trimming of low-incrementality Kids Soap campaigns. Focused bid raises on cleared, high-iota generic cells with available headroom.  
  rejections: {'no predicted gain from this raise': 4, 'no budget change possible': 2, 'over allowance': 2}  
  actions: {'reduce_budget': 8, 'reduce_cpm': 16}
- `l2p_nat_llm` r0 seed 101 run 4: Corrected prior rejections by restricting slot-1 leadership exclusively to cells meeting CLEARS/Tier A status and avoiding ≥80% slot-share blockers. Aligned market ownership to highest-IOTA SKUs per M-matrix flags. Prese  
  rejections: {'leader S cannot take slot': 1, 'no predicted gain from this raise': 1}  
  actions: {'increase_budget': 2, 'increase_cpm': 7, 'reduce_budget': 5, 'reduce_cpm': 12}
- `l2p_nat_llm` r0 seed 101 run 5: Corrects known wrong-holder misallocations by routing high-iota keywords to efficient scale/fund SKUs (S1, S4) while trimming low-value hold/trim spend (S3, S5) to protect the direct ROAS floor. Market shifts reallocate   
  rejections: {'G: already at slot  on >= % of impressions': 5, 'no predicted gain from this raise': 4, 'leader S cannot take slot': 1}  
  actions: {'increase_cpm': 12, 'increase_budget': 2, 'reduce_cpm': 18, 'reduce_budget': 7}
- `l2p_nat_llm` r0 seed 101 run 6: Plan targets cells with verified bid headroom and slot shares under 80% to avoid previous G3 rejections. Contested markets with misaligned ownership are corrected via lead_market calls. Budgets are raised exclusively for  
  rejections: {'no predicted gain from this raise': 6, 'G: already at slot  on >= % of impressions': 3}  
  actions: {'increase_cpm': 6, 'reduce_cpm': 7}
- `l2p_nat_llm` r0 seed 202 run 1: Revised plan removes rejected raises on saturated/MISSES cells and focuses on fixing market share inefficiencies via lead_market actions where incumbent holders lack incremental value. Budget shifts unlock highly constra  
  rejections: {'lead_market needs sku_id, city_id and keyword': 6}  
  actions: {'increase_budget': 3, 'increase_cpm': 2, 'reduce_cpm': 5, 'reduce_budget': 5}
- `l2p_nat_llm` r0 seed 202 run 2: Corrected previous allowance violations by cutting low-performing hold/trim budgets first, then raising fund/scale campaigns that meet the ≥2 run-out rule. Resolved top contested markets where wrong holders held premium   
  rejections: {'over allowance': 3, 'no predicted gain from this raise': 3}  
  actions: {'increase_cpm': 6, 'reduce_cpm': 9, 'reduce_budget': 2}
- `l2p_nat_llm` r0 seed 202 run 3: Plans shifts capital from holding/low-iota campaigns (S3/S5) to fund/scale roles, while correcting contest markets where higher-iROAS SKUs are disadvantaged. Bid raises focus on thin cells with clear mROAS upside and avo  
  rejections: {'no predicted gain from this raise': 11, 'over allowance': 1}  
  actions: {'increase_cpm': 7, 'increase_budget': 3, 'reduce_budget': 3, 'reduce_cpm': 22}
- `l2p_nat_llm` r0 seed 202 run 4: Plan pivots to aggressive scaling of high-iota S2 Body Wash cells across DEL/PUN/MUM while securing budget headroom for capped fund campaigns (S1-HYD, S4-HYD, S4-BLR). Contested market corrections (HYD K01/K09, BLR K05)   
  rejections: {'no predicted gain from this raise': 6, 'over allowance': 1}  
  actions: {'increase_budget': 3, 'increase_cpm': 5, 'reduce_cpm': 7, 'reduce_budget': 5}
- `l2p_nat_llm` r0 seed 202 run 5: Budget increases confined strictly to fund campaigns running out daily. Market leadership shifts optimize incremental yield in contested Body Wash generic slots, while yields reduce low-iota Soap brand displacement.  
  rejections: {'no predicted gain from this raise': 5}  
  actions: {'increase_budget': 3, 'increase_cpm': 3, 'reduce_cpm': 5, 'reduce_budget': 4}
- `l2p_nat_llm` r0 seed 202 run 6: Deployed spend room into high-iota generic cells across Scale campaigns and corrected contested market leadership to highest-incrementality SKUs. Held/trimmed weaker holdings to protect portfolio floor ROAS while maximiz  
  rejections: {'no predicted gain from this raise': 5, 'G: already at slot  on >= % of impressions': 1}  
  actions: {'increase_cpm': 2, 'reduce_cpm': 9, 'reduce_budget': 1}
