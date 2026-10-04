## X2 Ablation [confirm2001_tally] — 10 worlds, outcome = scored offtake

Negative vs_l0 = removing/isolating the component hurts. CI = Student-t; p = exact sign-flip (smallest possible 2/2^n); mde = this comparison's own 80%-power minimum detectable effect.

| arm | vs_l0_pct | vs_l0_t95 | p | mde | worse/better seeds | vs_no_op_pct | vs_no_op_t95 | floor_met | min_roas_margin | mean_spend_vs_l0_pct |
|---|---|---|---|---|---|---|---|---|---|---|
| no_op | -0.116 | -0.21 … -0.02 | 0.027 | 0.113 | 8/2 | 0.000 | 0.00 … 0.00 | 9/10 | -0.027 | 7.318 |
| l0 | 0.000 | 0.00 … 0.00 | 1.000 | 0.000 | 0/0 | 0.116 | 0.02 … 0.21 | 10/10 | 0.304 | 0.000 |
| sm_r1500_c1.0 | 0.322 | 0.23 … 0.41 | 0.002 | 0.110 | 0/10 | 0.438 | 0.31 … 0.56 | 10/10 | 0.287 | 3.701 |
| gate_min2000 | 0.384 | 0.29 … 0.48 | 0.002 | 0.117 | 0/10 | 0.501 | 0.38 … 0.62 | 10/10 | 0.286 | 4.586 |
| gate_min3000 | 0.445 | 0.32 … 0.57 | 0.002 | 0.155 | 0/10 | 0.562 | 0.41 … 0.71 | 10/10 | 0.282 | 5.440 |