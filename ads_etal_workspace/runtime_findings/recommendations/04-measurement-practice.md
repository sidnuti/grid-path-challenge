# Measurement and process rules (learned during this work)

1. **Use Student-t CIs and exact sign-flip p at small n.** The percentile bootstrap understated spread at n=6. The smallest possible
   sign-flip p at n=6 is 0.031; compute each comparison's own minimum detectable effect from its own spread (not another comparison's).
2. **Report floor compliance and margin with every lift.** A missed ROAS floor voids the score, so lift alone is incomplete. Every X2 table
   has `floor_met` and `min_roas_margin`; keep it that way. No-op itself misses the floor in 3/20 and 1/10 fresh worlds.
3. **Never reuse a seed set for confirmation.** Seeds 101/202, 303-322, 1001-1010 and 2001-2010 are all spent; write the selection rule
   down before touching a new set, run it once, and say how many candidates share it.
4. **Replicate before believing.** The "cuts are net-negative" reading (dev6, +0.13pp) did not replicate on 20 fresh worlds (+0.05, CI spans 0);
   the gate result did (+0.85 / +0.86). Treat any single 6-world result as a hypothesis.
5. **Judge a rule on its thin cases.** A rule can pass on average and still void the score in the worst world (fixed 3000, seed 1002).
   Include thin-margin worlds on purpose.
6. **Stamp results with the code hash** (`runs.py`) and re-run when `harness/` changes; the harness was edited by another session during
   this work and an equivalence test caught real drift.
7. **Check before trusting a plan: test-first on the measurement layer.** Oracle exact-match, A/A = 0, and "switchable policy equals
   the real policy" tests caught the budget-truncation effect and the harness drift early.
8. **Coordinate parallel sessions.** Two sessions launched overlapping confirmations on the same seeds; agree who owns each run, and share
   cache keys (same arm names and hash) so nothing is simulated twice.
9. **Do not edit `harness/` from the experiments.** Report fixes as proposals with evidence (this folder).
