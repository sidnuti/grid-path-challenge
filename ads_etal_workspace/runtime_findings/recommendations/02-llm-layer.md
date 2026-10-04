# LLM layer: recommendations

**Do not run the paid LLM slice as configured.** Scripted stand-ins ($0, depth L2, 6 dev worlds, paired vs L0; `results/x5_llm_aided.md` in
`experiments/results/`): no arm improves offtake significantly. Best arm: L3 random +0.021% (CI -0.012..0.054). Oracle leaves (answers from
hidden truth) are at or below zero: L1 0.000, L2 -0.000, L3 -0.002, L6 -0.030 (default) / -0.061 (recalibrated), L4 -0.033. Always-veto L6
-0.056 (CI excludes 0). Floor met 6/6 everywhere; 0 fallbacks. A real model can only be as good as the oracle at these trigger rates.

| # | Recommendation | Why | Limit |
|---|---|---|---|
| L1 | Hold the $3 real-LLM run until the triggers change | L1/L2/L6 fire about 0.3 / 1 / 0.2 times per run, too rarely to matter | Evidence is scripted, not a real model |
| L2 | Redesign what the leaves decide, not just how often they fire | Recalibration (explore on, review threshold 300) raises triggers (L4 ~30, L6 ~3 per world) but acting leaves *lower* offtake even with oracle answers | Oracle answers are proxies (value per impression x 1000 / CPM), not the best possible answers |
| L3 | Do not let L6 veto raises; do not enable L4 explore without evidence | both lower offtake in every scripted arm | Proxy oracle |
| L4 | Gate L2 (shock) on OSA only | the detector is reliable only for stock-outs / OSA (X1.6); price and demand flags are mostly false positives | 6 worlds; one shock schedule |
| L5 | Build a better-than-proxy oracle before concluding leaves are useless | the bound is only as strong as the truth mapping | Medium effort |
| L6 | If the paid slice is ever run: $3 cap, record then replay, only for leaves that show non-negative oracle value | cost control | Gate on L5 |
