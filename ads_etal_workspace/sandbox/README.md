> **WIP snapshot, 2026-10-05** (branch `arnab/wip-chimera-mohoLLM`). Chimera R-C2 is complete (18 runs); MoHOLLM R-M1 is **partial**
> (about 11 of 16 jobs finished when this was taken; the MoHOLLM cache and `ledger.jsonl` are mid-run copies). See `REPLICATION_REPORT.md`
> for results and findings, and `artifacts/replication_report.html` for the interim report.
>
> **What is not in this folder** (to keep it small): the upstream code copies (`chimera/upstream`, `mohollm/upstream`; recopy them from
> the repos named in each `UPSTREAM.txt` at the recorded commit, never edit them), the `.venv`s, per-run console logs, `tools/tla2tools.jar`
> (TLA+ v1.8.0 from the tlaplus GitHub releases, sha256 `c2fe4e56...8239`), and MoHOLLM's per-run result CSVs (only `result.json` is kept).
>
> **Restore the record/replay caches** (needed for `SANDBOX_LLM_MODE=replay`, i.e. re-running recorded results at $0):
> `mkdir -p cache && for f in cache_archive/*.tar.gz; do tar xzf $f -C cache; done`
> The OpenRouter key is never stored here; it is read from `OPENROUTER_API_KEY` or `grid-path-challenge/.env`.

# sandbox/ — replicate Chimera and MoHOLLM, then adapt (see `plan_copies/2026-10-05_replicate_adapt_extend_plan.md`)

Upstream code is **copied** (never edited) under `chimera/upstream/` and `mohollm/upstream/`
(commit hashes in each `UPSTREAM.txt`). Everything we add lives in `adapters/`, `tests/`, `runs/`, `common/`.
Bugs found in upstream are patched at import time in `adapters/` and logged in `REPLICATION_REPORT.md`.

## Environments (uv, Python 3.11)
```
cd sandbox/chimera && uv sync && uv run pytest -m offline -q
cd sandbox/mohollm && uv sync && uv run pytest -m offline -q
```
`common/` tests (transport, cache, ledger) run from either env: `uv run pytest ../common/tests -q`.

## LLM access (OpenRouter only)
`common/openrouter.py` is the single place a paid call can happen: an httpx transport under both
LangChain (Chimera) and the OpenAI SDK (MoHOLLM). `SANDBOX_LLM_MODE`:
`replay` (default; a cache miss is an error, never a live call) · `record` · `live`.
The key comes from `OPENROUTER_API_KEY` or `grid-path-challenge/.env`; it is never logged.
Cache: `sandbox/cache/<ledger item>/`. Replaying a recorded run costs $0 and is ledgered as `cached`.

## Ledger / budget ($25 programme cap)
`python -m common.ledger --summary` (run from `sandbox/`). The ledger is checked **before** every live call
(worst case = prompt/3 tokens + full `max_tokens`) and hard-stops at each item's sub-cap.
Prices are true OpenRouter per-token rates, with no fallback price for unknown models.

## Model
Both repos run on `minimax/minimax-m3` (user decision 2026-10-05; reasoning model, $0.30/$1.20 per M tokens). Paper model names
(`gpt-4o`, `gemini-2.0-flash`) are aliased to it in `common/openrouter.py`. See `REPLICATION_REPORT.md` for consequences.

## Gates
P0: envs import upstream · `pytest -m offline` collects · 3 pings ≤ $0.01 and ledgered · replay of the pings = $0.
P1: all offline tests green (or upstream bug documented + patched in adapters) · Chimera dynamics CSVs reproduce
exactly · `PAPER_TARGETS.md` written from the papers' tables.

## External dependencies (audited 2026-10-05)
| Need | Status |
|---|---|
| JDK (TLA+ proof only) | `brew install openjdk` → `/opt/homebrew/opt/openjdk` (keg-only; tests call that path directly) |
| `tools/tla2tools.jar` | TLA+ v1.8.0 release, sha256 `c2fe4e56…8239` |
| HuggingFace datasets | none used. Chimera data is bundled; NB201/fcnet are out of scope |
| TabPFN weights | `tabpfn-v2-regressor.ckpt` (42 MB, open, no license step) in `~/Library/Caches/tabpfn`, sha256 `2ab5a07d…`. The installed `tabpfn` 9.x defaults to the gated v3.5, so `adapters/ledger_hook.py` pins **v2** (the paper's version) on CPU. The LLM surrogate goes through OpenRouter as before; TabPFN is the local non-LLM surrogate for the R-M3 ablation |
