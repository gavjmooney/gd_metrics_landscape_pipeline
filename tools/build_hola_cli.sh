#!/usr/bin/env bash
# Build hola_cli from tools/hola_cli.cpp.
#
# Required:
#   ADAPTAGRAMS_DIR  Path to the adaptagrams/cola source tree containing
#                    libdialect/, libavoid/, libcola/, libtopology/, libvpsc/
#                    each with a built .libs/ directory. (See
#                    https://github.com/mjwybrow/adaptagrams for build
#                    instructions; the libdialect README covers the chain.)
#
# Optional:
#   OUT  Output binary path. Default: $(repo_root)/.venv/bin/hola_cli when
#        a venv is active, else /tmp/hola_cli.
#
# After a successful build, point the layout pipeline at the binary by
# either putting it on PATH as `hola_cli` or exporting HOLA_CLI=<path>.

set -euo pipefail

if [ -z "${ADAPTAGRAMS_DIR:-}" ]; then
    echo "error: ADAPTAGRAMS_DIR must point at the adaptagrams/cola source tree" >&2
    echo "       (the directory containing libdialect/, libavoid/, libcola/, ...)" >&2
    exit 2
fi
ADAPT="$ADAPTAGRAMS_DIR"

for lib in libdialect libavoid libcola libtopology libvpsc; do
    if [ ! -d "$ADAPT/$lib/.libs" ]; then
        echo "error: $ADAPT/$lib/.libs not found — did you build adaptagrams?" >&2
        exit 2
    fi
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO_ROOT/tools/hola_cli.cpp"
OUT="${OUT:-${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/hola_cli}}"
OUT="${OUT:-/tmp/hola_cli}"

echo "building $SRC -> $OUT"
echo "  ADAPTAGRAMS_DIR=$ADAPT"

g++ -std=gnu++11 -O2 -Wall \
    -I"$ADAPT" \
    "$SRC" \
    -L"$ADAPT/libdialect/.libs" \
    -L"$ADAPT/libavoid/.libs" \
    -L"$ADAPT/libcola/.libs" \
    -L"$ADAPT/libtopology/.libs" \
    -L"$ADAPT/libvpsc/.libs" \
    -ldialect -lavoid -lcola -ltopology -lvpsc \
    -Wl,-rpath,"$ADAPT/libdialect/.libs" \
    -Wl,-rpath,"$ADAPT/libavoid/.libs" \
    -Wl,-rpath,"$ADAPT/libcola/.libs" \
    -Wl,-rpath,"$ADAPT/libtopology/.libs" \
    -Wl,-rpath,"$ADAPT/libvpsc/.libs" \
    -o "$OUT"

echo "ok: $OUT"
echo
echo "next: export HOLA_CLI=$OUT  (or symlink it onto PATH as hola_cli)"
