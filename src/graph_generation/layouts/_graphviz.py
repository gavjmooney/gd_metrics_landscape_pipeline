"""Helpers for graphviz / pydot layouts (dot binary discovery + dot parsing)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Tuple


def resolve_dot() -> str:
    explicit = os.environ.get("GRAPHVIZ_DOT")
    if explicit and Path(explicit).exists():
        return explicit
    candidates = [
        # Native Windows paths — Path() treats these as POSIX strings on
        # WSL, so the WSL-mounted variants below are what actually
        # resolve when the pipeline runs under WSL against a Windows
        # Graphviz install.
        r"C:\Program Files\Graphviz\bin\dot.exe",
        r"C:\Program Files (x86)\Graphviz\bin\dot.exe",
        "/mnt/c/Program Files/Graphviz/bin/dot.exe",
        "/mnt/c/Program Files (x86)/Graphviz/bin/dot.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    on_path = shutil.which("dot")
    if on_path:
        return on_path
    raise RuntimeError(
        "dot binary not found - install Graphviz and either add its bin "
        "folder to PATH, or set GRAPHVIZ_DOT to the dot binary path"
    )


def resolve_sfdp() -> str:
    explicit = os.environ.get("GRAPHVIZ_SFDP")
    if explicit and Path(explicit).exists():
        return explicit
    candidates = [
        r"C:\Program Files\Graphviz\bin\sfdp.exe",
        r"C:\Program Files (x86)\Graphviz\bin\sfdp.exe",
        "/mnt/c/Program Files/Graphviz/bin/sfdp.exe",
        "/mnt/c/Program Files (x86)/Graphviz/bin/sfdp.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    on_path = shutil.which("sfdp")
    if on_path:
        return on_path
    raise RuntimeError(
        "sfdp binary not found - install Graphviz and either add its bin "
        "folder to PATH, or set GRAPHVIZ_SFDP to the sfdp binary path"
    )


def parse_edge_pos(pos: str) -> List[Tuple[float, float]]:
    pts: List[Tuple[float, float]] = []
    for tok in pos.split():
        if tok.startswith(("s,", "e,")):
            continue
        x, y = tok.split(",")
        pts.append((float(x), float(y)))
    return pts


def trim_endpoint_anchors(pts, u_xy, v_xy):
    if u_xy is not None and len(pts) >= 2:
        d_first = (pts[0][0] - u_xy[0]) ** 2 + (pts[0][1] - u_xy[1]) ** 2
        d_second = (pts[1][0] - u_xy[0]) ** 2 + (pts[1][1] - u_xy[1]) ** 2
        if d_first < d_second:
            pts = pts[1:]
    if v_xy is not None and len(pts) >= 2:
        d_last = (pts[-1][0] - v_xy[0]) ** 2 + (pts[-1][1] - v_xy[1]) ** 2
        d_penult = (pts[-2][0] - v_xy[0]) ** 2 + (pts[-2][1] - v_xy[1]) ** 2
        if d_last < d_penult:
            pts = pts[:-1]
    return pts
