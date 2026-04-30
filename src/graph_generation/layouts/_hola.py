"""Helpers for HOLA layout via the libdialect Python binding (or shim)."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

import networkx as nx

from .base import Bends, NotApplicable, Positions


def _close(p: Tuple[float, float], q: Tuple[float, float]) -> bool:
    return abs(p[0] - q[0]) < 1e-3 and abs(p[1] - q[1]) < 1e-3


def to_tglf(G: nx.Graph) -> Tuple[str, Dict]:
    nid_to_int = {nid: i for i, nid in enumerate(sorted(G.nodes))}
    lines: List[str] = []
    for nid, idx in nid_to_int.items():
        lines.append(f"{idx} 0.0 0.0 30.0 30.0")
    lines.append("#")
    for u, v in G.edges:
        lines.append(f"{nid_to_int[u]} {nid_to_int[v]}")
    lines.append("#")
    return "\n".join(lines) + "\n", nid_to_int


def parse_tglf(text: str, nid_to_int: Dict) -> Tuple[Positions, Bends]:
    int_to_nid = {i: nid for nid, i in nid_to_int.items()}
    raw = [ln.strip() for ln in text.splitlines()
           if ln.strip() and not ln.strip().startswith("//")]
    sections: List[List[str]] = [[]]
    for ln in raw:
        if ln == "#":
            sections.append([])
        else:
            sections[-1].append(ln)
    positions: Positions = {}
    bends: Bends = {}
    if sections and sections[0]:
        for ln in sections[0]:
            toks = ln.split()
            if len(toks) < 5:
                continue
            try:
                idx = int(toks[0])
                cx, cy = float(toks[1]), float(toks[2])
            except ValueError:
                continue
            if idx in int_to_nid:
                positions[int_to_nid[idx]] = (cx, cy)
    if len(sections) >= 2 and sections[1]:
        for ln in sections[1]:
            toks = ln.split()
            if len(toks) < 2:
                continue
            try:
                u_int = int(toks[0])
                v_int = int(toks[1])
            except ValueError:
                continue
            if u_int not in int_to_nid or v_int not in int_to_nid:
                continue
            u, v = int_to_nid[u_int], int_to_nid[v_int]
            rest = toks[2:]
            pts: List[Tuple[float, float]] = []
            for i in range(0, len(rest) - 1, 2):
                try:
                    pts.append((float(rest[i]), float(rest[i + 1])))
                except ValueError:
                    break
            u_xy = positions.get(u)
            v_xy = positions.get(v)
            if u_xy is not None:
                while pts and _close(pts[0], u_xy):
                    pts.pop(0)
            if v_xy is not None:
                while pts and _close(pts[-1], v_xy):
                    pts.pop()
            if pts:
                bends[(u, v)] = pts
    return positions, bends


def run_hola(G: nx.Graph) -> Tuple[Positions, Bends]:
    """Run HOLA on G, returning (positions, bends).

    Tries the ``hola`` Python package first; on ImportError, falls back
    to the ``libdialect_cli`` binary if HOLA_CLI is set or the binary
    is on PATH. Otherwise raises NotApplicable.
    """
    try:
        import hola  # type: ignore
    except ImportError:
        hola = None  # noqa: F841
    else:
        try:
            return _via_python(G)
        except Exception as e:
            raise NotApplicable(f"hola python binding failed: {e}") from e

    cli = os.environ.get("HOLA_CLI")
    if not cli:
        import shutil
        cli = shutil.which("hola_cli")
    if not cli or not Path(cli).exists():
        raise NotApplicable(
            "HOLA backend not available; install the 'hola' python package "
            "or build libdialect_cli and set HOLA_CLI to its path"
        )
    return _via_cli(G, cli)


def _via_python(G: nx.Graph) -> Tuple[Positions, Bends]:
    import hola  # type: ignore
    tglf, nid_to_int = to_tglf(G)
    out = hola.layout_tglf(tglf)
    return parse_tglf(out, nid_to_int)


def _via_cli(G: nx.Graph, cli: str) -> Tuple[Positions, Bends]:
    tglf, nid_to_int = to_tglf(G)
    with tempfile.NamedTemporaryFile("w", suffix=".tglf", delete=False) as fin:
        fin.write(tglf)
        in_path = fin.name
    out_path = in_path + ".out.tglf"
    try:
        cp = subprocess.run(
            [str(cli), "--in", in_path, "--out", out_path],
            capture_output=True, text=True, timeout=120,
        )
        if cp.returncode != 0:
            raise RuntimeError(
                f"hola_cli rc={cp.returncode}: "
                f"{(cp.stderr or cp.stdout).strip()[:300]}")
        with open(out_path, "r", encoding="utf-8") as f:
            text = f.read()
    finally:
        for p in (in_path, out_path):
            try:
                os.unlink(p)
            except OSError:
                pass
    return parse_tglf(text, nid_to_int)
