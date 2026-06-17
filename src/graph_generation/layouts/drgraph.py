"""DRGraph multilevel layout (Zhu et al. 2020, IEEE TVCG).

Shells out to the upstream ``Vis`` binary. The C++ source has no
``-seed`` flag, so the algorithm is stochastic but unseedable from
Python — runs are not bit-reproducible across invocations. Build the
binary via ``tools/install_drgraph.sh``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple

import networkx as nx

from .base import Layout, NotApplicable, Positions, register_layout


def _resolve_drgraph_bin() -> str:
    explicit = os.environ.get("DRGRAPH_BIN")
    if explicit and Path(explicit).exists():
        return explicit
    on_path = shutil.which("drgraph") or shutil.which("Vis")
    if on_path:
        return on_path
    raise NotApplicable(
        "drgraph binary not found; build it via tools/install_drgraph.sh "
        "and either put it on PATH as `drgraph` or set DRGRAPH_BIN"
    )


def _write_input(G: nx.Graph, path: Path) -> dict:
    nid_to_int = {nid: i for i, nid in enumerate(sorted(G.nodes()))}
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{G.number_of_nodes()} {G.number_of_edges()}\n")
        for u, v in G.edges():
            f.write(f"{nid_to_int[u]} {nid_to_int[v]} 1\n")
    return nid_to_int


def _parse_output(path: Path, nid_to_int: dict) -> Positions:
    int_to_nid = {i: nid for nid, i in nid_to_int.items()}
    positions: Positions = {}
    with open(path, "r", encoding="utf-8") as f:
        header = f.readline().split()
        if len(header) < 2 or int(header[1]) != 2:
            raise RuntimeError(f"unexpected drgraph output header: {header!r}")
        for i, line in enumerate(f):
            toks = line.split()
            if len(toks) < 2:
                continue
            nid = int_to_nid.get(i)
            if nid is None:
                continue
            positions[nid] = (float(toks[0]), float(toks[1]))
    return positions


def _drgraph(G: nx.Graph, seed: int) -> Tuple[Positions, None]:
    bin_path = _resolve_drgraph_bin()
    with tempfile.TemporaryDirectory() as td:
        in_path = Path(td) / "graph.txt"
        out_path = Path(td) / "layout.txt"
        nid_to_int = _write_input(G, in_path)
        # Mirror the upstream README's graph-layout invocation
        # (mode=1, A=2, B=1) on a sample budget that fits our n<=75
        # corpus. The binary has no -seed flag.
        cp = subprocess.run(
            [
                str(bin_path),
                "-input", str(in_path),
                "-output", str(out_path),
                "-mode", "1",
                "-samples", "400",
                "-neg", "5",
                "-gamma", "0.1",
                "-A", "2",
                "-B", "1",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if cp.returncode != 0:
            raise RuntimeError(
                f"drgraph rc={cp.returncode}: "
                f"{(cp.stderr or cp.stdout).strip()[:300]}"
            )
        if not out_path.exists():
            raise RuntimeError(
                f"drgraph produced no output file at {out_path}"
            )
        return _parse_output(out_path, nid_to_int), None


LAYOUT = register_layout(Layout(
    name="drgraph", backend="drgraph", fn=_drgraph,
    stochastic=True, timeout_s=10.0,
))
