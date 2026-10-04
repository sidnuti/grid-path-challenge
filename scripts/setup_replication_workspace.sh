#!/usr/bin/env bash
# Recreate the sibling layout the experiment code expects:
#   <ws>/grid-path-challenge/   this repo (gpc, harness, harness_l2p, llm_cache, .venv)
#   <ws>/experiments/ ...       copied from ads_etal_workspace/
# experiments/lib/runs.py and x8_run.py resolve paths as <ws>/grid-path-challenge and <ws>/experiments,
# so the two must be real sibling directories (copies, not symlinks: the code calls Path.resolve()).
#
#   scripts/setup_replication_workspace.sh ~/gpc_ws
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
WS="${1:?usage: $0 <workspace-dir>}"
mkdir -p "$WS"
rsync -a --exclude ads_etal_workspace --exclude .venv "$REPO/" "$WS/grid-path-challenge/"
rsync -a "$REPO/ads_etal_workspace/" "$WS/"
cd "$WS/grid-path-challenge"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
echo "workspace ready: $WS"
echo "next: cd $WS/grid-path-challenge && see REPLICATION.md"
