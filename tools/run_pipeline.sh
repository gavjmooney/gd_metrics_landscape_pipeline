#!/usr/bin/env bash
# One-shot pipeline runner.
#
# Usage:
#   tools/run_pipeline.sh [OUTPUT_DIR] [--seed N] [--stages SPEC]
#                          [--parallel-layouts N]
#
# OUTPUT_DIR defaults to $EFFECTS_OUT, then to ./output.
# --seed N overrides [pipeline].seed for this run only by writing a
# temp config; config/pipeline.toml is left untouched.
# --stages SPEC selects which stages to run (default: all). Forms:
#     --stages all                 every stage (default)
#     --stages layout              single stage
#     --stages from:layout         this stage onward
#     --stages layout,metrics      explicit comma list (passed via --only)
# Valid stage names: generate, stage, sample, dedup, layout, metrics.
# --parallel-layouts N clamps [layouts].parallel_layouts to N. If
# omitted, the script reads /proc/meminfo and auto-caps the value
# to fit in RAM (each layout subprocess peaks ~2 GB RSS, so 12 of
# them on a 16 GB WSL ceiling will OOM-kill the user session — as
# happened before this auto-cap existed). Override the per-layout
# memory estimate or system reserve via the env vars
# ``PIPELINE_LAYOUT_RSS_GB`` (default 2.5) and
# ``PIPELINE_MEM_RESERVE_GB`` (default 3).
#
# Validates the environment (Python, venv, OGDF, HOLA), reports
# actionable setup steps for anything missing, then launches
# the selected stages and streams progress to the terminal while also
# persisting a copy at <OUTPUT_DIR>/run.log.

set -euo pipefail

# ---- pretty output ----
if [[ -t 1 ]]; then
    G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; B='\033[1;34m'; D='\033[2m'; X='\033[0m'
else
    G=''; Y=''; R=''; B=''; D=''; X=''
fi
ok()    { printf "${G}✓${X} %s\n" "$*"; }
warn()  { printf "${Y}!${X} %s\n" "$*" >&2; }
fail()  { printf "${R}✗${X} %s\n" "$*" >&2; }
info()  { printf "${B}→${X} %s\n" "$*"; }
hint()  { printf "  ${D}%s${X}\n" "$*"; }

die() { fail "$*"; exit 1; }

# ---- parse args ----
# Accept OUTPUT_DIR positionally (back-compat) plus --seed N,
# --stages SPEC, --parallel-layouts N anywhere.
SEED_OVERRIDE=""
STAGES_SPEC="all"
PARALLEL_LAYOUTS_OVERRIDE=""   # empty = auto-detect from /proc/meminfo
POSITIONAL=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --seed)
            [[ $# -ge 2 ]] || die "--seed requires a value"
            SEED_OVERRIDE="$2"; shift 2 ;;
        --seed=*)
            SEED_OVERRIDE="${1#--seed=}"; shift ;;
        --stages)
            [[ $# -ge 2 ]] || die "--stages requires a value"
            STAGES_SPEC="$2"; shift 2 ;;
        --stages=*)
            STAGES_SPEC="${1#--stages=}"; shift ;;
        --parallel-layouts)
            [[ $# -ge 2 ]] || die "--parallel-layouts requires a value"
            PARALLEL_LAYOUTS_OVERRIDE="$2"; shift 2 ;;
        --parallel-layouts=*)
            PARALLEL_LAYOUTS_OVERRIDE="${1#--parallel-layouts=}"; shift ;;
        --)
            shift; POSITIONAL+=("$@"); break ;;
        *)
            POSITIONAL+=("$1"); shift ;;
    esac
done
set -- "${POSITIONAL[@]:-}"

if [[ -n "$PARALLEL_LAYOUTS_OVERRIDE" ]]; then
    [[ "$PARALLEL_LAYOUTS_OVERRIDE" =~ ^[1-9][0-9]*$ ]] \
        || die "--parallel-layouts must be a positive integer, got: $PARALLEL_LAYOUTS_OVERRIDE"
fi

if [[ -n "$SEED_OVERRIDE" ]]; then
    [[ "$SEED_OVERRIDE" =~ ^[0-9]+$ ]] \
        || die "--seed must be a non-negative integer, got: $SEED_OVERRIDE"
fi

# Translate --stages SPEC into the CLI's argv form.
#   "all"          → run all
#   "from:STAGE"   → run from:STAGE
#   "A,B,C"        → run --only A,B,C
#   single name    → run <name>
# Validation of stage names lives in the python CLI (planned_stages
# raises on unknown stages); we only check the shape here.
RUN_ARGS=()
case "$STAGES_SPEC" in
    "")
        die "--stages must not be empty (use 'all' for the full chain)" ;;
    all)
        RUN_ARGS=(run all) ;;
    from:*)
        [[ "$STAGES_SPEC" != "from:" ]] \
            || die "--stages from: requires a stage name (e.g. from:layout)"
        RUN_ARGS=(run "$STAGES_SPEC") ;;
    *,*)
        RUN_ARGS=(run --only "$STAGES_SPEC") ;;
    *)
        RUN_ARGS=(run "$STAGES_SPEC") ;;
esac

# ---- locate repo root ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

CONFIG="$REPO_ROOT/config/pipeline.toml"
[[ -f "$CONFIG" ]] || die "config not found at $CONFIG (are you in the right repo?)"

# Apply --seed override by writing a temp config; the original is
# untouched. The regex anchors on `^seed[[:space:]]*=` so it touches
# the [pipeline].seed line and not [sample].seed_offset.
if [[ -n "$SEED_OVERRIDE" ]]; then
    EFFECTIVE_CONFIG="$(mktemp --suffix=.toml)"
    trap 'rm -f "$EFFECTIVE_CONFIG"' EXIT
    sed -E "s/^(seed[[:space:]]*=[[:space:]]*).*/\1${SEED_OVERRIDE}/" \
        "$CONFIG" > "$EFFECTIVE_CONFIG"
else
    EFFECTIVE_CONFIG="$CONFIG"
fi

# ---- resolve OUTPUT_DIR ----
OUTPUT_DIR_INPUT="${1:-${EFFECTS_OUT:-$REPO_ROOT/output}}"
# Translate Windows-style paths (e.g. D:/foo or D:\foo) into WSL paths.
# Without this, `tools/run_pipeline.sh D:/pipeline-output-4` from WSL
# falls into the "relative path" branch below and silently writes to
# <repo>/D:/pipeline-output-4 instead of D:\pipeline-output-4 — which
# starts a fresh corpus in the wrong place.
if [[ "$OUTPUT_DIR_INPUT" =~ ^[A-Za-z]:[/\\] ]]; then
    if command -v wslpath >/dev/null 2>&1; then
        translated="$(wslpath -u "$OUTPUT_DIR_INPUT")"
    else
        # Manual fallback: D:/foo -> /mnt/d/foo. Lower-case the drive
        # letter and replace backslashes with forward slashes.
        drive_letter="$(printf '%s' "${OUTPUT_DIR_INPUT:0:1}" | tr 'A-Z' 'a-z')"
        rest="${OUTPUT_DIR_INPUT:2}"
        rest="${rest//\\//}"
        rest="${rest#/}"
        translated="/mnt/${drive_letter}/${rest}"
    fi
    info "translated Windows path: $OUTPUT_DIR_INPUT → $translated"
    OUTPUT_DIR_INPUT="$translated"
fi
case "$OUTPUT_DIR_INPUT" in
    /*) OUTPUT_DIR="$OUTPUT_DIR_INPUT" ;;
    *)  OUTPUT_DIR="$REPO_ROOT/$OUTPUT_DIR_INPUT" ;;
esac
mkdir -p "$OUTPUT_DIR"

info "repo:    $REPO_ROOT"
info "config:  $CONFIG"
info "output:  $OUTPUT_DIR"
echo

# ---- platform check ----
case "$(uname -s)" in
    Linux*) ok "platform: Linux ($(uname -r))" ;;
    *)
        fail "platform: $(uname -s) — pipeline requires Linux (use WSL2 on Windows)"
        hint "OGDF and HOLA backends are Linux shared libs."
        exit 1 ;;
esac

# ---- python ----
if ! command -v python3 >/dev/null; then
    fail "python3 not found"
    hint "install: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi
PY_VER="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
PY_MAJ="$(python3 -c 'import sys;print(sys.version_info[0])')"
PY_MIN="$(python3 -c 'import sys;print(sys.version_info[1])')"
if (( PY_MAJ < 3 || (PY_MAJ == 3 && PY_MIN < 9) )); then
    die "python $PY_VER too old (need ≥ 3.9)"
fi
ok "python:   $PY_VER ($(command -v python3))"

# ---- venv ----
VENV="$REPO_ROOT/.venv"
if [[ ! -x "$VENV/bin/python" ]]; then
    info "venv missing — creating at $VENV"
    python3 -m venv "$VENV" || die "python3 -m venv failed (need python3-venv?)"
    "$VENV/bin/pip" install --upgrade pip wheel >/dev/null
    info "installing pipeline package (this may take a few minutes)..."
    "$VENV/bin/pip" install -e "$REPO_ROOT" || die "pip install -e . failed"
    ok "venv:     created and populated"
else
    ok "venv:     $VENV"
fi
PIPELINE_BIN="$VENV/bin/pipeline"
if [[ ! -x "$PIPELINE_BIN" ]]; then
    info "pipeline console script missing — reinstalling"
    "$VENV/bin/pip" install -e "$REPO_ROOT" || die "pip install -e . failed"
fi
ok "pipeline: $PIPELINE_BIN"

# ---- OGDF backend ----
check_ogdf() {
    "$VENV/bin/python" - <<'PY' 2>&1
try:
    from ogdf_python import ogdf  # noqa: F401
except Exception as e:
    print(f"FAIL: {type(e).__name__}: {e}")
    raise SystemExit(1)
print("OK")
PY
}

ogdf_msg="$(check_ogdf || true)"
if grep -q '^OK' <<< "$ogdf_msg"; then
    ok "OGDF:     loads cleanly${OGDF_INSTALL_DIR:+ (OGDF_INSTALL_DIR=$OGDF_INSTALL_DIR)}"
else
    # Try common install locations
    found=""
    for cand in "${OGDF_INSTALL_DIR:-}" \
                "$HOME/.layout_wsl_venv" \
                "$HOME/adaptagrams/ogdf-build" \
                "/usr/local" "/usr"; do
        [[ -z "$cand" ]] && continue
        if [[ -f "$cand/lib/libOGDF.so" && -f "$cand/lib/libCOIN.so" ]]; then
            found="$cand"; break
        fi
    done
    if [[ -n "$found" ]]; then
        export OGDF_INSTALL_DIR="$found"
        # retry
        if grep -q '^OK' <<< "$(check_ogdf || true)"; then
            ok "OGDF:     loads (auto-detected OGDF_INSTALL_DIR=$found)"
        else
            warn "OGDF: libs found at $found but ogdf_python still fails to load"
            hint "diagnostic:  python -c 'from ogdf_python import ogdf'"
        fi
    else
        warn "OGDF backend not loadable — FMMM, sugiyama, planarization-ortho, pivot-MDS, radial-tree will be skipped (n/a)"
        hint "ogdf_python error: ${ogdf_msg#FAIL: }"
        hint "fix: build OGDF from https://github.com/ogdf/ogdf and either install"
        hint "     to /usr/local OR set OGDF_INSTALL_DIR=<path containing lib/libOGDF.so>"
        hint "     (the layout_wsl_venv convention: ~/.layout_wsl_venv/{lib,include})"
    fi
fi

# ---- HOLA backend ----
HOLA_PATH="${HOLA_CLI:-$(command -v hola_cli || true)}"
if [[ -z "$HOLA_PATH" && -x "$VENV/bin/hola_cli" ]]; then
    HOLA_PATH="$VENV/bin/hola_cli"
fi
if [[ -n "$HOLA_PATH" && -x "$HOLA_PATH" ]]; then
    export HOLA_CLI="$HOLA_PATH"
    ok "HOLA:     $HOLA_PATH"
else
    warn "HOLA backend not found — HOLA layout will be skipped (n/a)"
    hint "fix: build the binary once via tools/build_hola_cli.sh"
    hint "     ADAPTAGRAMS_DIR=\$HOME/adaptagrams/cola bash tools/build_hola_cli.sh"
    hint "     (writes .venv/bin/hola_cli; needs adaptagrams/cola source)"
fi

# ---- DRGraph backend ----
# Resolution order matches src/graph_generation/layouts/drgraph.py:
#   1. $DRGRAPH_BIN if set and exists
#   2. `drgraph` or `Vis` on PATH
# We additionally fall back to $VENV/bin/drgraph (where install_drgraph.sh
# writes by default in an active venv) and export DRGRAPH_BIN so worker
# subprocesses inherit the resolved path even if PATH gets pruned.
DRGRAPH_PATH=""
if [[ -n "${DRGRAPH_BIN:-}" && -x "${DRGRAPH_BIN}" ]]; then
    DRGRAPH_PATH="$DRGRAPH_BIN"
elif command -v drgraph >/dev/null 2>&1; then
    DRGRAPH_PATH="$(command -v drgraph)"
elif command -v Vis >/dev/null 2>&1; then
    DRGRAPH_PATH="$(command -v Vis)"
elif [[ -x "$VENV/bin/drgraph" ]]; then
    DRGRAPH_PATH="$VENV/bin/drgraph"
fi
if [[ -n "$DRGRAPH_PATH" ]]; then
    export DRGRAPH_BIN="$DRGRAPH_PATH"
    ok "drgraph:  $DRGRAPH_PATH"
else
    warn "drgraph backend not found — drgraph layout will be skipped (n/a)"
    hint "fix: build the binary once via tools/install_drgraph.sh"
    hint "     sudo apt install build-essential cmake libgsl-dev libboost-program-options-dev"
    hint "     bash tools/install_drgraph.sh"
    hint "     (writes .venv/bin/drgraph; clones ZJUVAI/DRGraph)"
fi

# ---- show seed + sanity-check config ----
SEED="$(grep -E '^seed[[:space:]]*=' "$EFFECTIVE_CONFIG" | head -1 | sed -E 's/[^0-9]//g')"
if [[ -n "$SEED_OVERRIDE" ]]; then
    ok "seed:     ${SEED:-unknown} (overridden via --seed)"
else
    ok "seed:     ${SEED:-unknown}"
fi

# ---- auto-cap parallel_layouts against available RAM ----
# Each layout subprocess peaks at ~2 GB RSS (one OOM-killed process
# in dmesg measured 1.97 GB anon-rss). Without a cap, the default
# parallel_layouts=12 against WSL2's 16 GB ceiling OOM-kills the user
# session — observed once, fixed by this block.
#
# Manual override (--parallel-layouts N) takes priority. Otherwise
# compute a safe N from MemTotal:
#   safe = max(1, floor((MemTotal_GB - reserve) / per_layout_GB))
#   final = min(safe, config.parallel_layouts)
# Defaults can be tuned via PIPELINE_LAYOUT_RSS_GB and
# PIPELINE_MEM_RESERVE_GB env vars; they only matter when no
# --parallel-layouts override is given.
LAYOUT_RSS_GB="${PIPELINE_LAYOUT_RSS_GB:-2.5}"
MEM_RESERVE_GB="${PIPELINE_MEM_RESERVE_GB:-3}"

# Read parallel_layouts from the EFFECTIVE config (post --seed
# rewrite), defaulting to 1 if the line is missing. The grep tolerates
# whitespace around the =.
CFG_PL="$(awk -F= '/^[[:space:]]*parallel_layouts[[:space:]]*=/ {
    gsub(/[^0-9]/, "", $2); print $2; exit }' "$EFFECTIVE_CONFIG")"
CFG_PL="${CFG_PL:-1}"

# Read RAM total. /proc/meminfo reports kB. Use awk for float math
# so we don't have to add bc as a dependency.
MEM_TOTAL_KB="$(awk '/^MemTotal:/ {print $2; exit}' /proc/meminfo 2>/dev/null || echo 0)"
MEM_TOTAL_GB="$(awk -v kb="$MEM_TOTAL_KB" 'BEGIN { printf "%.1f", kb / 1024 / 1024 }')"

SAFE_PL="$(awk -v t="$MEM_TOTAL_GB" -v r="$MEM_RESERVE_GB" -v p="$LAYOUT_RSS_GB" '
BEGIN {
    budget = t - r
    if (budget < p) { print 1; exit }
    n = int(budget / p)
    if (n < 1) n = 1
    print n
}')"

if [[ -n "$PARALLEL_LAYOUTS_OVERRIDE" ]]; then
    FINAL_PL="$PARALLEL_LAYOUTS_OVERRIDE"
    ok "parallel_layouts: $FINAL_PL (manual --parallel-layouts override)"
elif (( SAFE_PL < CFG_PL )); then
    FINAL_PL="$SAFE_PL"
    warn "parallel_layouts: auto-capped from $CFG_PL to $FINAL_PL"
    hint "system has ${MEM_TOTAL_GB} GiB; budget=$(awk -v t=$MEM_TOTAL_GB -v r=$MEM_RESERVE_GB 'BEGIN{printf "%.1f", t-r}') GiB"
    hint "after reserving ${MEM_RESERVE_GB} GiB, ${LAYOUT_RSS_GB} GiB/layout fits ${FINAL_PL} workers"
    hint "set --parallel-layouts N or PIPELINE_LAYOUT_RSS_GB=... to tune"
else
    FINAL_PL="$CFG_PL"
    ok "parallel_layouts: $FINAL_PL (within RAM budget of $(awk -v t=$MEM_TOTAL_GB -v r=$MEM_RESERVE_GB 'BEGIN{printf "%.1f", t-r}') GiB)"
fi

# Pass the override through to the CLI. Without this the python side
# would read parallel_layouts straight from the TOML and ignore our
# clamp. cmd_run rejects values < 1 so FINAL_PL never falsely zeroes.
RUN_ARGS+=(--parallel-layouts "$FINAL_PL")

echo
info "starting: pipeline ${RUN_ARGS[*]}"
echo

# ---- run ----
LOG="$OUTPUT_DIR/run.log"
export EFFECTS_OUT="$OUTPUT_DIR"

# Pin Python's hash seed so dict / set iteration is deterministic
# across processes. Without this, every Python subprocess gets a
# different ``hash(str)`` salt, and any code path that iterates a
# set/dict of hashable items (network's planarity / embedding
# routines, our own stagers that defaultdict(set), etc.) produces a
# different output per invocation. Verified empirically: under
# random hash, the same planar graph + same code yielded 3 different
# metric values across 5 subprocesses; under PYTHONHASHSEED=0 the
# same 5 yielded byte-identical results.
#
# This is set after argument parsing so the user can still override
# it via env (e.g. PYTHONHASHSEED=random for an ablation that
# explicitly wants the previous behaviour).
export PYTHONHASHSEED="${PYTHONHASHSEED:-0}"
ok "PYTHONHASHSEED=$PYTHONHASHSEED (pinned for cross-process reproducibility)"

# Run in foreground so the script blocks until the pipeline finishes
# (or the user Ctrl+C's). stdbuf keeps line-buffering through `tee`.
# Trap Ctrl+C so we can exit cleanly without dumping a stack trace.
trap 'echo; warn "interrupted — pipeline children may still be exiting"; exit 130' INT TERM

stdbuf -oL -eL "$PIPELINE_BIN" "${RUN_ARGS[@]}" --config "$EFFECTIVE_CONFIG" 2>&1 \
    | tee -a "$LOG"
RC=${PIPESTATUS[0]}

echo
if (( RC == 0 )); then
    ok "pipeline finished successfully"
    info "manifest: $OUTPUT_DIR/manifest.csv"
    info "metrics : $OUTPUT_DIR/metrics/"
    info "log     : $LOG"
else
    fail "pipeline exited with rc=$RC"
    info "log: $LOG  (tail it for details)"
    exit "$RC"
fi
