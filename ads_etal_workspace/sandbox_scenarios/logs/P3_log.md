# P3 log: Track-A black box, baselines, oracle, MoHOLLM adapter ($0)

Spec: `design/04_experiment_protocol.md` §2–§6, `design/03_goals_macro_micro.md` §1, §4. Plan: P3.
Code:
- `bench/`: `decode.py`, `sim.py`, `goals.py`, `blackbox.py`, `design.py`, `arms.py`
- `mohollm/adapters/`: `grid_market.py`, `ads_configs.py`, `ads_acq.py`, `scripted_ads_llm.py`
- `mohollm/runs/r_ads.py`
- Tests: `mohollm/tests/test_ads_bench.py`

Outputs: `results/p3/`.

## Decisions (deviations from doc 04 §2.1, all logged in `bench/decode.py`)
- **E1:** 3 regions use 2 stick-breaking dimensions, so x is 10-d. G1 adds `budget_scale`, making 11-d.
- **Bid anchor:** bids anchor to the starting (warm-up) bids. "× live bid", re-decoded each run, compounds (1.5^6 ≈ 11×). The policy is stationary in x and adapts only through observations: the live window and the conquest signal.
- **Budget:**
  - E1 daily budget = B/day = warm-up spend per day, so Spend ≤ B, since budgets are caps.
  - Within a region the budget follows each campaign's warm-up spend (see fix 2).
- **Daypart:** a 3-level schedule, because the simulator has no per-daypart bid modifier.
- **K01 defence:** keys on an observable conquest signal, the inflation of K01's slot-1 clearing CPM against warm-up.
- **No guardrails under G-0/G-1:** the black box runs without guardrails, keeping only the physical bid bounds [₹200, ₹10k]. Doc 03: the direct-ROAS floor and the step limits are G-2 constraints. Constraint slacks C1, C3, C5–C9 are recorded on every evaluation for E3. C2 and C4 need the guardrail projection (P4).
- **G-1 objectives:**
  - f2 = share of auctions S5 wins at slot 1 on {K08, K01, K03} in DEL, from a new hidden `truth_slot1` table, search-share weighted by daypart.
  - f3 = S6 units sold / initial stock.
- **MoHOLLM minimises everything,** so F = −objective, scaled to ₹ lakh and %.
- **E1 is single-objective in MoHOLLM:** ScoreRegion + FunctionValueACQ, because ScoreRegionRHVC raises an error with fewer than 2 metrics.
- **Evaluation budget:** 5 shared Sobol points + 5 per trial (top_k 5), so 50 evaluations = 9 trials.

## Entries

### 2026-10-05: build and fixes
1. **Black-box smoke showed spend only 75–85% of B at the neutral point** (all levers at 0.5).
   - Cause 1: budget was split within a region by *starting* budgets, so over-funded campaigns hoarded budget they could not spend. Fix: split by warm-up spend.
   - Cause 2: the neutral point gives the North 50% of budget against a 32% demand share.
   - At warm-up region shares, sc1 spends 97% of B. CODE_VERSION bumped to p3.2.
2. **Real P2 bug surfaced:** `score_v2.score()` crashed adding S6 salvage into an int64 per-SKU series (pandas 3 refuses the upcast).
   - P2 tests missed it, because the readout computed salvage separately.
   - Fixed by casting to float. Regression test added: `gpc/tests/v2/test_p2.py::test_score_includes_salvage_for_ephemeral_stock`.
3. **Upstream finding:** `RandomACQ` ignores `top_k` and returns one int. The partitioned loop then fails with `TypeError` at `space_partitioning_mohollm.py:142`, so upstream's random ablations must keep an LLM surrogate.
   - For a $0 random-in-leaf A5, `adapters/ads_acq.py` registers `RandomTopKACQ` at runtime. Upstream is untouched.
4. **`cma` 3.2.2 fails under numpy 2** (`copy=False`), and MoHOLLM's pinned pymoo 0.6.0 pins `cma==3.2.2`.
   - O1 runs from the gpc environment (cma 4.5.0).
   - The two environments have identical numpy/pandas/scipy (2.4.6 / 3.0.6 / 1.17.1). The same x gives the identical IncRev in both (₹1,391,964 on sc1 seed 7 at warm-up shares).
5. **Test bugs fixed:** a pandas Series compared to `pytest.approx`, and zsh not word-splitting `$args` in my smoke loop.

### Cross-checks
- A0 "hold" (starting set-up, guardrail-free bench loop) scores IncRev ₹1,443,985 on sc1 seed 7. That equals the P2 scorer on the legacy runner's no-op exactly. This is now a test.
- A0 traversal (legacy policy with guardrails): ₹1,467,666 on sc1 seed 7.
- After 20 evaluations the best decoded point (A2, ₹1.39M) is still below hold. The starting set-up is not exactly inside the encoding, because the decoder caps budgets at warm-up spend. O1 measures how far the encoding can go.

### Smoke runs ($0, 20 evaluations, seed 7)

| Arm | Problem | LLM calls | Time | Best IncRev |
|---|---|---|---|---|
| A4 scripted | sc1 G0 | 33 (≈ 11 per trial) | 14 s | ₹1.06M |
| A3 scripted | sc1 G0 | 6 | 16 s | ₹1.12M |
| A4 scripted | sc_all G1 | 32 | 25 s | — |
| A3 scripted | sc_all G1 | 6 | 22 s | — |
| A5 | sc1 G0 | 0 | — | ₹1.33M |
| A5 | sc_all G1 | 0 | — | — |
| A1 | sc1 | — | — | ₹1.16M |
| A2 | sc1 | — | — | ₹1.39M |

Scripted-LLM values are meaningless as optimisation results; they only prove the loop runs.

### Tests
`mohollm/tests/test_ads_bench.py`: 17 passed (142 s). They cover:
- simplex, decoder purity and bounds, budget totals and region split, festive lever and live window, defence rule, encoding dimensions;
- hold = legacy runner + scorer; black-box determinism and fork isolation; cache key and hits; no out-of-window spend;
- adapter interface and negation; validity checks never simulate; configs for single- and multi-objective; RandomTopKACQ;
- end to end offline for A4 G0, A4 G1, A3 G0 and A5 G0 (shared initial design, in-box proposals, LLM-call accounting).
