## X2 Ablation [fresh20] — 20 worlds, outcome = scored offtake

Negative vs_l0 = removing/isolating the component hurts. CI = Student-t; p = exact sign-flip (smallest possible 2/2^n); mde = this comparison's own 80%-power minimum detectable effect.

| arm | vs_l0_pct | vs_l0_t95 | p | mde | worse/better seeds | vs_no_op_pct | vs_no_op_t95 | floor_met | min_roas_margin | mean_spend_vs_l0_pct |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | -0.364 | -0.53 … -0.20 | nan | 0.220 | 16/4 | -0.233 | -0.44 … -0.03 | 20/20 | 0.107 | -4.922 |
| no_op | -0.130 | -0.23 … -0.03 | nan | 0.137 | 14/6 | 0.000 | 0.00 … 0.00 | 17/20 | -0.073 | 5.161 |
| l0 | 0.000 | 0.00 … 0.00 | nan | 0.000 | 0/0 | 0.131 | 0.03 … 0.23 | 20/20 | 0.201 | 0.000 |
| no_cuts | 0.048 | -0.03 … 0.13 | nan | 0.106 | 8/12 | 0.179 | 0.12 … 0.24 | 18/20 | -0.054 | 6.248 |
| no_headroom_gate | 0.864 | 0.74 … 0.99 | nan | 0.171 | 0/20 | 0.996 | 0.80 … 1.20 | 20/20 | 0.093 | 9.448 |
| no_gate_no_cuts | 1.063 | 0.94 … 1.19 | nan | 0.167 | 0/20 | 1.196 | 1.02 … 1.37 | 11/20 | -0.135 | 17.358 |