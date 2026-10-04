# Handoff notes: System 1 harness build (pick up here next turn)

Companion to `2026-10-02-system1-procllm-htn-harness-plan.md` (the approved plan).

## State at pause

- Plan approved. **No harness code written yet**, and no repo files have been edited.
- Done in `grid-path-challenge/.venv`: installed `openai 2.48.0`, `anthropic 0.125.0`, `python-dotenv`, `pydantic 2.13.5`. **Not yet added to `requirements.txt`**, which is M0's first step.
- Python is **3.9.6**, so avoid 3.10+ syntax (`match`, `X | Y` type unions at runtime without `from __future__ import annotations`).
- `git status`: only untracked `grid_path_challenge_brief.html` and `task/`. `gpc/` is pristine.
- Measured sim cost: a full 70-day simulation takes ≈ 18 s (no-op) / ≈ 28 s (baseline). The `make score` trio takes ~1–2 min.

## Decisions taken since the plan was written

1. **Sizing method.** Generate candidate actions per cell and campaign (bid options from `gpc.engine.traversal.choose_bids` options; budget raises for run-out campaigns). Project each with **`gpc.guardrails.project_actions`** (read-only import), so our projections match G8 exactly. Then select with a **Lagrangian multiple-choice knapsack**:
   - for each cell, pick the option maximising `ι·Δrev − μ·(floor·Δspend − Δrev)`;
   - binary-search μ so that Σ headroom use ≤ the run's allowance.
   - This replaces the `linprog` call (simpler; it handles cuts and raises jointly). Note the change in A1-implementation.md.
2. **Offtake value of an action** = `ι × Δad_revenue` (cannibalised ad orders add no offtake).
3. **Pre-checks** mirror G0/G3/G4/G5/G7 using constants imported from `gpc.guardrails` (`TOP_SLOT_SHARE`, `OSA_MIN`, `RUNOUT_MIN_DAYS`, step limits).

## Correction to carry into the docs (found while reading `market.py` mechanics)

**Sibling collision does not inflate price.** Clearing prices come from external competitor bids, so a lower Aurel sibling is displaced one slot down (it loses impressions) but is not charged more, and it does not raise the leader's price. Slot-13 share displaced beyond slot 13 is lost. So:

- the cost of self-competition is **futile follower raises** (the grid thinks the bid buys slot 1, but the sibling holds it) and a **wrong leader** (a low value-per-impression SKU holding slot 1);
- it is *not* "paying to outbid yourself";
- two siblings at slots 1 and 5 can actually *add* coverage.

Fix the wording in `problem-mapped/00-problem-map-and-recommendation.md` (SG3 row, D5) and `A-procllm-htn-harness.md` (S3). In the tools-only arm, SG3 becomes:

- no raises on followers where a sibling holds ≥ 80% of slot 1;
- the leader is the sibling with the best conv × ASP × ι per impression.

## Biggest expected levers for the tools-only arm (to validate first in M1)

1. **Budget-starved campaigns.** 6 campaigns ran out on all 28 warm-up days, losing evening demand. Raise their budgets where G5/G7 pass, sized by ι·m.
2. **Spending the headroom** (4.97× → ~4.65–4.70× target) on the highest ι·m generic cells.
3. **Faster competitor cuts**, with the money redeployed.
4. **No G3-blocked proposals.**

Iterate the tools-only policy on dev seed 7 plus seeds 11/23/42 before adding the LLM. Gate: floor met everywhere and lift ≥ baseline.

## Next-turn order

M0 scaffold (requirements, `.env.example`, `.gitignore`, Makefile targets, config/params, rules test) → M1 tools + `HTNToolsOnly` + sim iteration → M2 LLM layer (OpenRouter default; Anthropic/OpenAI by `.env`), replay, meter, faults → M3 leaves/methods + S1–S10 tests → M4 `harness_eval` + probes → M5 trace + S2 hooks → M6 docs (A1/A2/A3 + systems-1-2-3 roadmap).
