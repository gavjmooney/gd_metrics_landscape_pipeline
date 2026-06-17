#!/usr/bin/env python
"""Manual rebuild of ``<EFFECTS_OUT>/viewer.html`` from current SVGs.

The layout stage already rebuilds the viewer at the end of every
``pipeline run layout`` invocation; this script is the standalone
entry point for ad-hoc rebuilds (e.g. after dropping in extra
drawings, or to refresh a partial run mid-flight).

Usage:
    EFFECTS_OUT=/mnt/d/pipeline-output-2 \\
        python tools/build_viewer.py
    # then open ``viewer.html`` in a browser. SVGs load via relative
    # paths so the page works without a webserver.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    # Make sure the package is importable when run from a checkout.
    here = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(here / "src"))
    from graph_generation.viewer import build

    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path,
                    help="output HTML path (default: $EFFECTS_OUT/viewer.html)")
    ap.add_argument("--thumb-size", type=int, default=220,
                    help="CSS pixels per thumbnail (default 220)")
    ap.add_argument("--effects-out", type=Path,
                    default=Path(os.environ.get("EFFECTS_OUT", "./output")),
                    help="corpus output root (default $EFFECTS_OUT)")
    args = ap.parse_args(argv)

    n, target = build(args.effects_out, args.out, args.thumb_size)
    if n == 0:
        print("no SVGs found — make sure the layout stage has run with "
              "verify_drawings_per_source > 0", file=sys.stderr)
        return 1
    size_kb = target.stat().st_size / 1024
    print(f"wrote {target}  ({n:,} records, {size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
