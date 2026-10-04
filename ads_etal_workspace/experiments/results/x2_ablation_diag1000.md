## X2 Ablation [diag1000] — 10 worlds, outcome = scored offtake

Negative vs_l0 = removing/isolating the component hurts. CI = Student-t; p = exact sign-flip (smallest possible 2/2^n); mde = this comparison's own 80%-power minimum detectable effect.

| arm | vs_l0_pct | vs_l0_t95 | p | mde | worse/better seeds | vs_no_op_pct | vs_no_op_t95 | floor_met | min_roas_margin | mean_spend_vs_l0_pct |
|---|---|---|---|---|---|---|---|---|---|---|
| no_op | -0.081 | -0.22 … 0.06 | 0.230 | 0.178 | 6/4 | 0.000 | 0.00 … 0.00 | 7/10 | -0.079 | 4.842 |
| l0 | 0.000 | 0.00 … 0.00 | 1.000 | 0.000 | 0/0 | 0.081 | -0.06 … 0.23 | 10/10 | 0.140 | 0.000 |
| sm_r1500_c1.0 | 0.420 | 0.31 … 0.53 | 0.002 | 0.133 | 0/10 | 0.501 | 0.32 … 0.68 | 10/10 | 0.119 | 4.122 |
| sm_r3000_c4.0 | 0.617 | 0.50 … 0.74 | 0.002 | 0.147 | 0/10 | 0.699 | 0.50 … 0.90 | 10/10 | 0.057 | 6.427 |
| gate_min2000 | 0.695 | 0.51 … 0.88 | 0.002 | 0.228 | 0/10 | 0.777 | 0.51 … 1.05 | 10/10 | 0.047 | 7.431 |
| gate_min3000 | 0.763 | 0.56 … 0.96 | 0.002 | 0.249 | 0/10 | 0.845 | 0.56 … 1.13 | 9/10 | -0.015 | 8.315 |