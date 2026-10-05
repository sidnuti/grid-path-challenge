# Grid design simulator: scenarios, goals, MoHOLLM experiments and a compiler

> Date: 2026-10-05. Status: **design only**. Nothing here has been built or run, and no paid LLM calls were made.
> Inputs: the grid-path-challenge simulator (`grid-path-challenge/gpc/`), the hypercube/linkage work (`explore-and-understand/06_…`, `explore_eda/linkages/`), the Chimera and MoHOLLM sandboxes (`sandbox/`), the framework notes in `~/Documents/Exploration/ads-revenue/`, and a web survey of simulators, papers and practitioner reports.

## The ask, restated

1. Add scenarios to the grid market:
   - category-specific cannibalization;
   - brand ↔ product association ("butter ≈ Amul");
   - ephemeral / seasonal / festive categories;
   - and make macro vs micro goals specific.
2. Run MoHOLLM with **one global objective (iROAS)**.
3. Add sub-goals and sub-objectives; see how it performs.
4. Add constraints; test the hypothesis that MoHOLLM will not respect them and that a **compiler** is needed to enforce binding constraints.

## Documents

| # | File | What it settles |
|---|---|---|
| 01 | [Landscape and literature](01_landscape_and_literature.md) | What exists (AuctionGym, AdCraft, AuctionNet, RecSim NG, Chimera, MMMs), what the evidence says (Blake et al., Simonov et al., cannibalization-corrected attribution, constrained auto-bidding, LLMs on constraints), practitioner reports from quick commerce, and nine design rules D1–D9 |
| 02 | [Simulator v2](02_simulator_v2_design.md) | Nested-logit shelf with competitor SKUs (cannibalization), intent mix and reformulation (brand association), calendar with festive/ephemeral/seasonal mechanics, finite stock and pull-forward, competitor agents, optional halo, Scorer v2 with true brand-level incrementality; scenario files; build steps |
| 03 | [Goals: macro vs micro](03_goals_macro_micro.md) | Why "max iROAS" needs a budget; the typed goal record; macro vs micro by scope, horizon, owner and unit; prices as the link between them; conflict taxonomy; the G-0 → G-1 → G-2 goal ladder; the goal ledger |
| 04 | [Experiment protocol E1–E3](04_experiment_protocol.md) | 12-d decision encoding and decoder, two oracles, arms (random, BoTorch, MoHOLLM global/partitioned/random-in-leaf; six constraint-handling arms), metrics, eight pre-registered hypotheses, run design and cost control |
| 05 | [Compiler and verifier](05_compiler_and_verifier.md) | Four constraint classes with four different guarantees; load-time consistency, feasibility and multi-run reachability; verify → repair → project → trim → certify; how the verifier itself is verified; decision record; a CSL-like rule file |

## The argument in eight lines

1. Today's market has **one incrementality number per keyword** and **no shelf**: an ad can only cannibalize its own SKU. None of the four scenarios can exist in it ([02 §1](02_simulator_v2_design.md)).
2. The literature says incrementality is a property of **who searches** (Blake et al.) and **who else is on the page** (Simonov et al.). So v2 makes ι *emerge* from a nested-logit shelf plus an intent mix, instead of setting it ([01 §3](01_landscape_and_literature.md)).
3. That one change produces all three market scenarios:
   - sibling cannibalization (a nest strength λ);
   - "butter ≈ Amul" (a generic query mostly owned by one brand's loyalists, so the keyword label lies);
   - festive cold start, pull-forward and stock-outs (a calendar on top).
4. **iROAS must be scored at brand level and by counterfactual.** SKU-level ι over-states it by exactly the sibling share. The simulator computes the truth; policies never see it ([02 §7](02_simulator_v2_design.md)).
5. **"Max iROAS" alone is degenerate.** The global objective is max brand-incremental revenue at a fixed budget, which is the same as max iROAS at that budget ([03 §1](03_goals_macro_micro.md)).
6. **Macro and micro goals meet through prices:** λ (budget), μ (floor), ν_j (each micro goal). Every goal gets a sentence saying what it costs ([03 §3](03_goals_macro_micro.md)).
7. **MoHOLLM only knows box bounds.** Its one "constrained" benchmark (CarSideImpact) folds constraint violation into an objective, and its other benchmarks drop constraints. So we expect it to:
   - respect box constraints;
   - respect linear constraints only through how the decision vector is encoded;
   - violate outcome constraints during search, and sometimes in its final answer ([01 §3.6](01_landscape_and_literature.md), [04 §5](04_experiment_protocol.md)).
8. **A compiler fixes the first two exactly and the last one only probabilistically.** Action and state constraints hold by construction. Projected constraints hold on the projection. Realised-outcome constraints need a buffer and a calibration check. The repair code itself is verified, which is the lesson of Chimera's guardian bugs ([05](05_compiler_and_verifier.md)).

## Build order (all $0 until step 6)

| Step | Work | Gate |
|---|---|---|
| 1 | Simulator v2 modules A (shelf) and F (scorer v2), with `dev` reproduced exactly when the flags are off | legacy byte-identity; decomposition sums; `no_op` IncRev = 0 |
| 2 | Modules B (intent), C (calendar, stock), D (competitors); scenario files sc1–sc4, sc_all | calibration ranges; unit conservation; festive CPM 1.3–1.5× |
| 3 | Re-run the linkage EDA on v2 worlds and score recovery against truth (diversion, ownership π, reformulation) | the linkage report's trust levels become graded |
| 4 | Decoder, two oracles, arms A0–A2 and A5 (no LLM) | oracle gap measured; BO baseline curves |
| 5 | Compiler with G0–G8 + C1–C9, property tests, differential test against `guardrails.py` | soundness, idempotence, legacy equivalence |
| 6 | MoHOLLM pilot (2 evaluations per LLM arm, record → replay → project cost) | **user approval and a new ledger cap** |
| 7 | E1 → E2 → E3 | pre-registered hypotheses in [04 §5](04_experiment_protocol.md) |

## Relation to paused work

The Chimera R-C2 and MoHOLLM R-M1..R-M4 replication runs (sandbox plan) are still paused awaiting a scope decision. E1–E3 reuse the same harness (CachingTransport, ledger, `PYTHONHASHSEED=0`, content-seeded shuffles) and the same `qwen/qwen3.7-flash` choice. They do not depend on the replication finishing, but its findings 7–8 (inverted method naming, RHVC scorer) decide which MoHOLLM configuration E1 runs.

## Main sources

- Simulators: [AuctionGym](https://github.com/amazon-science/auction-gym) · [AdCraft](https://arxiv.org/abs/2306.11971) · [AuctionNet](https://arxiv.org/abs/2412.10798) · [RecSim NG](https://arxiv.org/abs/2103.08057) · [Robyn vs Meridian](https://mbuzz.co/articles/robyn-vs-meridian).
- Incrementality: [Blake, Nosko & Tadelis 2015](https://www.nber.org/system/files/working_papers/w20171/w20171.pdf) · [Simonov, Nosko & Rao](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2668265) · [Attributed, But Not Incremental (2026)](https://arxiv.org/abs/2606.26690).
- Constrained bidding: [Balseiro et al. 2024](https://proceedings.mlr.press/v235/balseiro24a.html) · [Deng et al. 2023](https://proceedings.mlr.press/v202/deng23c/deng23c.pdf).
- LLMs and constraints: [COMPASS](https://arxiv.org/abs/2510.07043) · [LLMs as formalizers](https://arxiv.org/pdf/2505.13252).
- Quick commerce practice: [festive ad rates](https://www.storyboard18.com/advertising/festive-rush-pushes-quick-commerce-ad-rates-up-30-40-as-brands-shift-more-digital-spend-108755.htm) · [festive premium](https://www.storyboard18.com/how-it-works/quick-commerce-ad-costs-soar-this-festive-season-ws-l-110678.htm) · [Inc42](https://inc42.com/features/blinkit-zepto-instamart-d2c-ad-strategy-festive-season/) · [dashboard ROAS](https://www.meerkats.ai/blog/quick-commerce-roas-truth/) · [availability](https://www.42signals.com/blog/visibility-on-quick-commerce-platforms/).

Each document ends with its own **Assumptions and caveats** table, as in the earlier reports.
