# P2 log: Modules B (intent), C (calendar + stock), D (competitors), public tables, scenarios

Spec: `design/02_simulator_v2_design.md` §3–§5, §7.2, §8, §10 steps 2–4, 6–7. Plan: `plan_copies/2026-10-05_sandbox_ads_e2e_plan.md` P2.
Outputs: `results/p2/`. Code: `gpc/` branch `ads/sim-v2`.

## Architecture carried over from P1 (README M1–M6)
- Ad-order counts come from the legacy auction (calibrated direct ROAS). The v2 modules change:
  - what the ads take (the decomposition);
  - search volumes (calendar, reformulation);
  - clearing prices (competitors);
  - availability (stock).
- New random draws use child streams `SeedSequence([seed, 1009, day, MODULE_ID])`, or world-level `SeedSequence([seed, MODULE_ID])`, so legacy streams never shift. Dev stays byte-identical (golden check after each module).

## Entries

### 2026-10-05: modules B/C/D wired, scenarios generated
- New modules: `gpc/calendar.py`, `stock.py`, `competitors.py`, `intent.py`, `world_v2.py`, `public_v2.py`.
  - `market.simulate_day` now runs in stages: auction (stage 1), reformulation, searches/impressions (stage 2), conquest loss, then pacing and orders as before.
  - The legacy goldens stayed byte-identical (32/32) after the restructure.
- The runner sends `pub_*` tables to `Observation.extra` and `truth_*` tables to `SimResult.truth_tables`.
- Scenario files come from `scripts/make_scenarios.py`.
- Design choices (deviations from doc 02):
  - D1: pull-forward `days_after` is 10, not 14, so the dip (days 60–69) stays inside the 70-day horizon.
  - D2: the intent mix changes the *split* of ad orders (M1 kept). sc2 raises K07's legacy intent to 2.0 to reproduce the "looks brand-like in direct ROAS" trap, and lowers K05's to 0.8.
  - D3: reformulation uses Aurel's pre-pacing ad visibility, because pacing needs searches, which need reformulation.
  - D4: competitor spend model `s·b^ε` with ε = 2.3, η = 0.5. Equilibrium bid = (budget/searches)^(1/ε).
  - D5: ad orders are filled first when S6 stock runs short. The facts table keeps the orders placed (paid), while sku_city_daily records units actually filled.
  - D6: conquest losses on brand queries are booked to the bar nest in `category_share_weekly`.
- Bug found in the smoke run: on ephemeral K11's non-live days a market formed with 0 searches, giving 0/0 in the shelf weights. Fixed: skip markets with no searches when the calendar is on.
- Smoke (seed 7, no-op), iROAS by scenario:

  | Scenario | iROAS |
  |---|---|
  | sc1 | 1.81 |
  | sc2 | 3.48 |
  | sc3 | 1.92 |
  | sc4 | 1.85 |
  | sc_all | 3.46 |

  sc2 and sc_all are high because, with all ads off, conquest of K01 starts and steals Aurel-loyal shoppers, so "defending K01" is counted in IncRev. This is the intended mechanism; its size is checked in calibration.

### 2026-10-05: calibration round 1, first readout (`logs/p2_readout_run1.txt`)
Five problems found and fixed:
1. **Festive CPM ratio was 1.09** (gate 1.3–1.5).
   - Cause: agent demand indices included ephemeral K11 (×6 surge, 0 outside its window), which swamped the index. The long tail was also frozen at 1.0.
   - Fix: index over core keywords only, and the long tail paces like an agent.
2. **S6 never stocked out** (about ₹600k of salvage), so the stock trap could not bite.
   - Fix: stock scaled ×0.65 of the doc values (D7). It now binds around days 58–59 in some cities under the starting bids.
3. **K01 defence worth about 17× its spend,** which dominated brand IncRev (sc2 iROAS 3.5).
   - Fix: low end of the doc ranges (σ_undef 0.20, presence 0.4) and `loyal_buy` 0.15 → 0.08 (D8). Defence is now worth 3–7× its spend; sc2 iROAS ≈ 2.2.
4. **K01 attributed ROAS fell when K03 was paused** (doc: should improve).
   - Added `reform_conv_mult` 2.0, since reformulators are high-intent.
   - The ROAS still dips 0.5–6% because of budget pacing. Freed S1/S3 budget keeps more Aurel entrants in K01 auctions later in the day, so own-brand collisions push impressions to lower slots, where ROAS is worse.
   - Reported as is (D9). The illusion shows up as *K01 attributed revenue +2–6% while brand offtake falls 2–3%*. The gate tests that form.
5. **Run-out share off.** sc3 was diluted (0.21) by S6 campaigns that cannot spend before launch; sc4 was inflated (0.38) by K12 cells added without budget.
   - Fix: measure over legacy campaigns only, and top up existing campaigns' budgets for new always-on cells (sized like `world._campaigns`).

### 2026-10-05: readout bug found during the round-2 check (`logs/p2_readout_run2.txt`)
- The readout's CPM formula still priced the long tail at 1.0 after fix 1 (reported 1.25).
- An offline sweep (calendar + agents only) gave 1.456 at η 0.5, ε 2.3. η ≥ 1 oscillates, so η stays at 0.5.
- Fixed the readout formula; the readout now shows 1.456.

### 2026-10-05: holdout lever, public tables, gates
- **`request_holdout`:**
  - G0 accepts it; it uses the same lever, projection and pause path as `pause_keyword`.
  - The runner restores the cell after one run and publishes `lift_readout`: true brand-incremental ₹/day of the cell over the week before, plus N(0, 0.25·|truth| + ₹300), with a 95% CI.
- **Bug:** in sc_all, the legacy guardrail grid divided 0/0 for S6 cells before launch (recorded OSA 0, so prior reach 0). Fixed by making direct ROAS an explicit NaN when there is no reach; non-zero values are unchanged and goldens are identical.
- **`tests/v2/test_p2.py`:** 22 gates.
  - Pull-forward conservation (exact); festive curve and ephemeral windows; seasonal peak.
  - Stock ≥ 0, with OSA 0 after a stock-out; S6/K11 absent outside their window.
  - Festive CPM in [1.3, 1.5] and recovers; legacy price shock kept.
  - Conquest: pausing K01 triggers it and costs more than 2× the spend saved; no conquest while Aurel defends.
  - π is a distribution with city tilt.
  - Traps: K07 label trap, reformulation illusion; decomposition still partitions orders.
  - Holdout pauses exactly one run and its readout appears in the next run; CI coverage ≥ 90% over 50 seeds.
  - `Observation.extra` carries public tables only, with the 7-day lag exact.
  - Counterfactual is deterministic with stateful modules.
  - Per-scenario speed and calibration.
- **Final:** goldens 32/32 byte-identical; `make test` 213 passed (`logs/p2_full_tests.txt`). The v2 suite also passes with RuntimeWarnings as errors.
- **Final readout:** `results/p2/readout.md` (6 scenarios × seeds 7/11/23). A world takes 4–6 s; sc2 and sc_all readouts run 3 worlds plus 2 probes in about 15–19 s.
