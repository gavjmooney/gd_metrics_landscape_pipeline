#!/usr/bin/env bash
# Build the DRGraph Vis binary (Zhu et al. 2020, IEEE TVCG).
#
# Upstream: https://github.com/ZJUVAI/DRGraph (no LICENSE file as of
# 2026 — treat as research code; do not redistribute the binary).
#
# System packages required (Debian/Ubuntu/WSL):
#   sudo apt install build-essential cmake libgsl-dev libboost-program-options-dev
#
# Optional env vars:
#   DRGRAPH_SRC  Where to clone DRGraph. Default: $HOME/src/DRGraph.
#   OUT          Output binary path. Default: $(repo_root)/.venv/bin/drgraph
#                when a venv is active, else /tmp/drgraph.
#
# After a successful build, point the layout pipeline at the binary by
# either putting it on PATH as `drgraph` or exporting DRGRAPH_BIN=<path>.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DRGRAPH_SRC="${DRGRAPH_SRC:-$HOME/src/DRGraph}"
OUT="${OUT:-${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/drgraph}}"
OUT="${OUT:-/tmp/drgraph}"

if [ ! -d "$DRGRAPH_SRC" ]; then
    echo "cloning ZJUVAI/DRGraph -> $DRGRAPH_SRC"
    mkdir -p "$(dirname "$DRGRAPH_SRC")"
    git clone --depth 1 https://github.com/ZJUVAI/DRGraph.git "$DRGRAPH_SRC"
fi

cd "$DRGRAPH_SRC"
mkdir -p build
unset DRGRAPH_GPU_COMPILE   # CPU build only; GPU path is upstream-marked unstable.
( cd build && cmake .. && make -j"$(nproc)" Vis )

BIN=""
for cand in "$DRGRAPH_SRC/Vis" "$DRGRAPH_SRC/build/Vis"; do
    if [ -x "$cand" ]; then BIN="$cand"; break; fi
done
if [ -z "$BIN" ]; then
    echo "error: build finished but no Vis binary found in $DRGRAPH_SRC{,/build}" >&2
    exit 1
fi

mkdir -p "$(dirname "$OUT")"
cp -f "$BIN" "$OUT"
echo "ok: $OUT"
echo
echo "next: export DRGRAPH_BIN=$OUT  (or symlink it onto PATH as drgraph)"
