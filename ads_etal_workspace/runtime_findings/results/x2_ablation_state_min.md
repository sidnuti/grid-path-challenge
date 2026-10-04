## X2 Ablation [state_min] — 20 worlds, outcome = scored offtake

Negative vs_l0 = removing/isolating the component hurts. CI = Student-t; p = exact sign-flip (smallest possible 2/2^n); mde = this comparison's own 80%-power minimum detectable effect.

| arm | vs_l0_pct | vs_l0_t95 | p | mde | worse/better seeds | vs_no_op_pct | vs_no_op_t95 | floor_met | min_roas_margin | mean_spend_vs_l0_pct |
|---|---|---|---|---|---|---|---|---|---|---|
| l0 | 0.000 | 0.00 … 0.00 | nan | 0.000 | 0/0 | 0.131 | 0.03 … 0.23 | 20/20 | 0.201 | 0.000 |
| sm_r1500_c1.0 | 0.530 | 0.45 … 0.61 | nan | 0.102 | 0/20 | 0.662 | 0.51 … 0.81 | 20/20 | 0.193 | 5.000 |
| sm_r1500_c2.0 | 0.605 | 0.52 … 0.69 | nan | 0.114 | 0/20 | 0.737 | 0.58 … 0.89 | 20/20 | 0.183 | 6.099 |
| sm_r1500_c4.0 | 0.637 | 0.55 … 0.73 | nan | 0.121 | 0/20 | 0.769 | 0.61 … 0.93 | 20/20 | 0.150 | 6.547 |
| gate_min2000 | 0.698 | 0.61 … 0.78 | nan | 0.113 | 0/20 | 0.830 | 0.67 … 0.99 | 20/20 | 0.148 | 7.179 |
| sm_r3000_c2.0 | 0.719 | 0.63 … 0.81 | nan | 0.117 | 0/20 | 0.851 | 0.69 … 1.02 | 20/20 | 0.147 | 7.425 |
| sm_r3000_c4.0 | 0.746 | 0.65 … 0.84 | nan | 0.131 | 0/20 | 0.878 | 0.70 … 1.05 | 20/20 | 0.142 | 7.802 |
| gate_min3000 | 0.800 | 0.70 … 0.90 | nan | 0.138 | 0/20 | 0.932 | 0.75 … 1.11 | 20/20 | 0.117 | 8.480 |