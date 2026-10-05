# Paper targets (fixed before any paid run)

Model for both replications: `minimax/minimax-m3` (user decision, 2026-10-05), so *absolute* numbers will not match the
papers' GPT-4o / Gemini-2.0-Flash runs. What can be tested is the **ordering / sign of each claim**, plus the repo's own
CSVs as a reference for the same code under the original model.

## Project Chimera — numeric targets exist (repo CSVs under `chimera/upstream/results/preprint_results/ecom/`)
All n = 1 run per arm, seed 42, 52 weeks, GPT-4o, temperature 0.9. No CIs in the source.

**T-C1 `comprehensive_three_agent/three_agent_summary.csv`** (total profit $, final trust, Δtrust)

| Agent | Bias | Profit | Final trust | Δtrust |
|---|---|---:|---:|---:|
| LLM-Only | volume | -99,090 | 1.000 | +0.277 |
| LLM+Guardian | volume | 657,847 | 0.691 | -0.009 |
| Full Chimera | volume | 1,515,266 | 0.716 | +0.018 |
| LLM-Only | margin | 1,623,682 | 0.359 | -0.328 |
| LLM+Guardian | margin | 1,695,826 | 0.631 | -0.068 |
| Full Chimera | margin | 1,960,078 | 0.795 | +0.108 |

**T-C2 `architecture_comparison/neutral_architecture_summary.csv`** (neutral bias): profit 1,342,315 / 1,688,563 / 1,894,900 and
weekly sd 10,870 / 7,450 / 4,869 for LLM-only / +Guardian / Full.

**T-C3 `trust_sensitivity/sensitivity_summary.csv`** (Full Chimera, 5 trust multipliers). Profit: 50K 2,215,620 · 100K 2,107,171 ·
150K 1,968,292 · 200K 2,050,229 · 300K 2,083,349.

Claims to test (ordinal, per bias): (1) LLM-only fails under bias (volume: loss; margin: trust collapse); (2) the guardian removes
the failure; (3) Full > Guardian in profit; (4) Full has the lowest weekly sd.

**Observations about the targets themselves** (found while reading, not yet tested):
- T-C3 labels 150K "Balanced — empirically optimal / maximizes risk-adjusted returns", but in the table 150K has the *lowest*
  profit of the five and 100K has the best Sharpe (8.27 vs 7.07). The code default is 120K, which is not in the sweep.
- The sweep is non-monotone in the multiplier (200K > 150K), consistent with n = 1 noise rather than a trend.
- `three_agent_summary.csv` LLM-only/volume ends with trust 1.000 and a *loss* — it is "safe on trust, bad on profit", not a trust failure.

## MoHOLLM (arXiv 2601.13892, Schwanke, Ivanov, Salinas, Hutter, Zela) — no numeric tables
Read via the arXiv abstract page and HTML version (extraction by a summarising model, not by eye; the PDF figures were not inspected).
- Main results are **figures only** (HV trajectories: Fig. 3 synthetic: DTLZ1, Branin–Currin, Chankong–Haimes, SchafferN1, Kursawe;
  Fig. 4 real-world: Penicillin, VehicleSafety, CarSideImpact). The paper has 9 tables, but none of the retrieved content gave
  per-method HV numbers, so **there is no fixed numeric target for HV**. Targets are therefore ordinal.
- Setup stated: Gemini-2.0-Flash, **10 seeds**, **50 evaluations incl. 5 initial**, k = 5 regions, N = 5 candidates/region, b = 4 evaluations/trial.
- Baselines: qLogEHVI, EHVI; NSGA-II/III, SPEA2, MOEA/D, GDE3, SMS-EMOA, IBEA, …; global-LLM optimiser.
- Ablations (Fig. 6): sample diversity, prompt variants (context / no-context / minimal), LLM vs random sampler, LLM vs GP vs TabPFN-v2 surrogate.
- Only quoted numbers: surrogate prediction Spearman 0.874, R² 0.757 (real-world tasks).

Claims to test (ordinal): (1) MoHOLLM HV > global LLM; (2) MoHOLLM ≈ NSGA-II / qLogEHVI; (3) ablation ordering from Fig. 6 (to be read off the figure
before the run); (4) LLM surrogate rank correlation on real-world tasks ≈ 0.87.

**Setup discrepancies that change the Phase 2 plan** (from the repo, see `REPLICATION_REPORT.md`):
- Paper: 10 seeds × 50 evals. Repo configs: `n_trials 15 × top_k 4 + 5 = 65` evals (partitioned), `13 × 4 + 5 = 57` (global). Repo scripts use seeds 31415927, 42, 6790.
- The problem list in the plan (ZDT1/2, VLMOP2) is not what the repo ships: no ZDT/VLMOP JSON configs, and `VLMOP` is VLMOP3.
