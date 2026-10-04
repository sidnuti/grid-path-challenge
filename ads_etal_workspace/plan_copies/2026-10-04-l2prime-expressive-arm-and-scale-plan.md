# Plan: L2′, an expressive LLM arm wired to L0 through an intent compiler, plus the scale report

## Context

The EDA (explore_eda/EDA_REPORT.md §10–11) showed where the offtake is:
- **Keyword-type incrementality:** brand ≈ 10%, generic ≈ 50%, competitor ≈ 99%.
- **SKU roles:** S1 is under-funded and capped. S3 and S5 are over-funded. S2 and S4 have the best incremental ROAS.
- **Sibling contests:** in 15 of 40 contested markets, the wrong sibling leads.
- **Other signals:** local surges, OSA dips, and unused floor headroom.

Today's L1/L2 leaves cannot act on any of this. They only *narrow or veto* L0 candidates: they rescale a raise, confirm a shock, break a tie, or veto. X5.1 showed that even **oracle** answers add ≈ 0 vs L0, because the leaves have nothing to choose between. They never propose a pause, a budget cut, a daypart change, a lead/yield switch, or a cross-SKU reallocation.

**Goal:** add **L2′**, an expressive arm. The LLM reads a compact, observation-only *state brief* and proposes a typed **intent plan** across all levers and scopes:
- SKU × city, keyword / keyword type (brand / competitor / generic), sub-category.

A deterministic **L0 intent compiler** (the interface that issues actions) turns intents into guardrail-safe actions. L2′ is an enabler, never an executor.

Then run three comparisons, with L1/L2 disabled in the L2′ arms:
- **L0** vs **L0 + L1/L2**;
- **L0 + L2′**;
- **L2′-native**: LLM-native exploration, with L0 acting only as compiler and safety.

Finally, write the report on scaling from 25 campaigns to 100s of SKU × city combinations to 500+ brands, with LLM cost capped.

**Decisions made:**
- **Code:** a sibling package `grid-path-challenge/harness_l2p/`. `harness/` is not edited; its tools are imported read-only.
- **Real LLM:** a cheap model, record+replay, **$10 hard cap**. Scripted/oracle bounds (cost $0) run first.

## Design

### Expressiveness ladder

| Layer | Can propose | Scope | Today |
|---|---|---|---|
| L0 | mechanical raises, cuts and budget raises from fixed rules | cell / campaign | built |
| L1/L2 | rescale, confirm, tiebreak or veto an L0 candidate | one cell / market | built; ≈ 0 value (X5.1) |
| **L2′** | any lever: CPM up/down, pause, budget up/down, dayparts, lead/yield a market, stance changes | SKU × city, keyword type, sub-category, market | **new** |

### `harness_l2p/brief.py`: state brief (deterministic, observation only)

Built from existing tools:
- `harness.tools.features.diagnose`: grid, verdicts, pacing, bids, options;
- `tools.incrementality.iota_lookup` / `fit_sku_incrementality`;
- `tools.siblings.markets`;
- `tools.shocks.detect_shocks`, with `own_action_days`;
- `tools.headroom.compute_headroom`.

Sections, each row with a stable `ref` id so intents can cite evidence:
1. Portfolio: dROAS to date, floor, headroom, allowance, run number.
2. **SKU × city role table**: offtake share, spend share, iROAS estimate (ad orders × ι × ASP ÷ spend), run-out rate, bid headroom (from `diag.options`), OSA, and the role (fund / hold / scale / trim). Logic ported from `explore_eda/eda/eda_tiers.py`, using `iota_lookup` in place of the full-sample regression.
3. Sub-category × keyword-type table: spend, dROAS, iROAS.
4. Contested markets: leader, best-iROAS sibling, gap, near-tie flag.
5. Anomalies: shocks (z, direction, own-action confound), OSA dips, reach trends per city × keyword, and cross-city lead/lag hints.
6. The lever menu with hard limits from `gpc.guardrails` constants (`BID_FLOOR/CEIL/STEP`, `BUDGET_UP/DOWN/MIN`, `TOP_SLOT_SHARE`, `OSA_MIN`).

The brief is capped at about 6k tokens: tables are rounded and the top-N rows kept by spend or anomaly size. It is digest-hashed, so an unchanged brief replays from cache.

### `harness_l2p/intents.py`: intent schema (pydantic, extends `harness.leaves.schemas.LeafSchema`)

```
IntentPlan { stance: [StanceRow], intents: [Intent] (≤ 25), notes }
Intent { id, verb ∈ {raise_bid, cut_bid, pause, raise_budget, cut_budget, set_dayparts, lead_market, yield_market, hold},
         scope {sku_id?, city_id?, keyword_id? | keyword_type? | sub_category?},
         size ∈ {small, medium, large} | target_slot ∈ {1,5,9,13} | dayparts[],
         evidence_refs[], confidence 0–1, expected_effect (text claim for the ledger) }
StanceRow { sub_category, keyword_type, sku_role, stance ∈ {defend_min, lead, scale, hold, trim, conquest, explore} }
```

Validation reuses `harness.leaves.schemas.validate_and_clip`:
- unknown ids are dropped;
- the intent count is clipped;
- a bad plan falls back to an empty plan.

### `harness_l2p/compiler.py`: L0 intent compiler (the action-issuing interface)

1. Expand the scope to cells/campaigns. A keyword type or sub-category expands to its matching cells.
2. Map verb + size to a concrete value:
   - **bids:** pick a step from `diag.options` (small ±10%, medium ±20%, large ±40%, or the cheapest bid reaching `target_slot`);
   - **budgets:** sized from `pacing` absorption;
   - **all values:** clamped to G1/G2/G6.
3. `lead_market` / `yield_market` becomes a raise for the leader plus cuts or holds for followers. This is the existing sibling hold mechanics, with the leader chosen by the LLM.
4. Merge with L0 candidates according to the mode, resolving one action per lever (G0):
   - `augment`: intents override L0 on conflict;
   - `native`: intents only.
5. Economics:
   - `tools.sizing.project_candidates` gives Δspend and Δrev;
   - raises compete in `select_raises` under the headroom allowance;
   - cuts and pauses free allowance.
6. `tools.precheck.filter_precheck`. Rejections (with reasons) go back to the LLM for **one** repair round (`params.verify_max_repairs`).
7. Emit actions with `reason = "L2P:<intent_id>"` and a compile report: kept, clamped, rejected and why.

### `harness_l2p/planner.py` + `rules_planner.py` + `policy.py`

- **planner:** renders `prompts/L2P_plan.v1.md` (system and user, loaded the same way as `harness/leaves/render.py`). It calls `harness.leaves.run.leaf(...)` through `harness.llm` components: Provider → Faults → Meter (with a `price_usd_per_mtok` override for the chosen model) → ReplayClient. Up to 2 calls per run: plan + repair.
- **rules_planner:** emits intents deterministically from the EDA §10.4 stance table, using brief roles and iROAS. This is the **LLM ablation**: does the LLM beat its own deterministic intent generator?
- **`L2PHarness(Policy)`:**
  - modes: `augment` | `native` | `rules`;
  - L1/L2 are always off;
  - fail-soft: any L2′ failure returns the **L0 actions** (`harness.policy._tools_only_recommend`), and an exception there falls back to `DeterministicTraversal`;
  - the trace extends `RunTrace` fields with the brief digest, intents, compile report and usage.

### Experiment (X8 · L2′), in `experiments/`, our code

**Arms:**

| Arm | What it is |
|---|---|
| `baseline` | the challenge's baseline (cached) |
| `l0` | tools only (cached) |
| `l12_real` | existing `HTNHarness` depth L2, real model |
| `l2p_aug` | L0 + L2′, augment mode |
| `l2p_native` | L2′ + compiler only (LLM-native exploration) |
| `l2p_rules` | deterministic intent generator (LLM ablation) |
| scripted bounds | `l2p_{aug,native}_{hold,random,oracle}`; oracle intents come from `World.truth`, offline only |

**Worlds:**
- dev6 (seeds 7/11/23/42/101/202), for comparability with X2/X5;
- plus 3 perturbed X7.3 worlds;
- the best arm is confirmed once on fresh seeds **3001–3006**, recorded in the seed ledger.

LLM arms run 3 replicates.

**Metrics:**
- paired lift vs `l0` and `baseline` (t-CI, sign-flip), floor met, min floor margin;
- proposed / shipped actions, compile-reject rate, guardrail block rate;
- intents by verb × keyword type × SKU role; levers used (pause / budget cut / daypart);
- cells touched outside the L0 candidate set;
- agreement across replicates;
- iROAS-weighted spend shift, read offline via `experiments/lib/oracle.py`;
- $/run, tokens, calls, wall-clock.

**Gates:**

| Gate | When | Condition | If it fails |
|---|---|---|---|
| A | before any paid call | `l2p_*_oracle` beats `l0` by more than the MDE (~0.1pp) | report and stop paying |
| B | during paid runs | cumulative spend reaches $10 | runner aborts |

**Cost estimate:**
- per call: ~6–8k input + ~1.5k output tokens;
- volume: 2 calls/run × 6 runs × 9 worlds × 3 replicates × 2 LLM arms ≈ 650 calls;
- that is ~6M tokens, about **$2–5** on a cheap model;
- `l12_real` is tiny (≈ 40 leaf calls/world).

### Scale report: `system_design_proposals/03_l2prime_expressiveness_and_scale.md` + artifact

1. Expressiveness ladder.
2. Intent DSL and compiler contract.
3. Brand / competitor / generic stance per sub-category × SKU role.
4. X8 results.
5. **Scaling.** The decision grain stays cell-level and deterministic. The LLM call unit is **brand × sub-category brief + event triggers** (anomaly, near-tie, role change, launch). Cost per brand-week is `calls × tokens × price` at low/mid/high, using X8's measured tokens. The three scale points:

   | Scale | Shape | Size |
   |---|---|---|
   | Today | 5 SKUs × 5 cities | 25 campaigns, 110 cells |
   | Hundreds of SKU × city | ~50 SKUs × 10 cities | ~2.5k cells |
   | 500+ brands | many brands | 250k–1M cells |

6. **Cost controls:**
   - per-brand $/week cap via the Meter;
   - brief-digest caching, so no call is made when nothing changed;
   - model routing (cheap by default, escalate only when gain − cost > 0, per the Cost-Aware Routing deck);
   - batching by sub-category;
   - distillation of stable intents into L0 rules via the promotion loop (design Part 3).
7. Latency vs the 15-minute stage: briefs run in parallel per brand.
8. Risks and what does not transfer.

## Files

**New:**
- `grid-path-challenge/harness_l2p/{__init__,brief,intents,compiler,planner,rules_planner,policy}.py`
- `grid-path-challenge/harness_l2p/prompts/L2P_plan.v1.md`
- `grid-path-challenge/tests/harness_l2p/{test_rules,test_intents,test_compiler,test_policy}.py`
- `experiments/x8_l2prime/x8_run.py`
- `system_design_proposals/03_l2prime_expressiveness_and_scale.md`

**Edited (ours):**
- `experiments/lib/arms.py` (l2p arms);
- `experiments/lib/scripted_llm.py` (L2P scripted modes);
- `runtime_findings/results/x8_l2prime.md` (output).

**Reused, not edited:**
- harness tools listed above;
- `harness.leaves.run.leaf`, `harness.leaves.schemas.validate_and_clip`;
- `harness.llm.{providers,faults,meter,replay}`;
- `harness.policy._tools_only_recommend`;
- `experiments/lib/{runs,stats,funnel,report,oracle}.py`.

## Verification

1. `pytest tests/harness_l2p -q`, covering:
   - AST isolation: no `gpc.market` / `scenarios` / `harness_eval` / `experiments` imports, and no `.truth`;
   - schema clip/drop;
   - each verb compiles to the right lever within G1/G2/G6, and conflicts resolve to one action per lever;
   - precheck parity;
   - `FAULT_INJECT=*` gives L0's exact actions (an S9b analogue);
   - `native` with an empty plan ships no LLM actions;
   - the existing `pytest tests -m "not slow"` suite still passes.
2. `make score POLICY=harness_l2p.policy:L2PHarness` with `LLM_MODE=off` equals L0 (augment) or no-op plus safety (native).
3. Run X8 scripted bounds ($0) → gate A → real runs in `record` mode → re-run in `replay` mode to confirm reproducibility, with identical numbers.
4. The report's cost table uses the measured tokens and $ from X8 traces. Run the mermaid parse check on the new doc, then publish the artifact.
