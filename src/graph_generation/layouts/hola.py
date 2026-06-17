"""HOLA (Kieffer et al. 2016) human-like orthogonal layered layout."""

from __future__ import annotations

import networkx as nx

from ._hola import run_hola
from .base import Layout, register_layout


def _hola(G: nx.Graph, seed: int):
    positions, bends = run_hola(G)
    return positions, bends or None


LAYOUT = register_layout(Layout(
    name="HOLA", backend="hola", fn=_hola, stochastic=False,
    # 10s wall-time cap per graph. HOLA shells out to ``hola_cli``
    # (libdialect/libavoid); on dense graphs it routinely runs many
    # minutes per graph and occasionally trips an internal C++
    # assertion that aborts the binary. The outer subprocess wrapper
    # in _run_one is the primary cap; ``_via_cli``'s subprocess.run
    # timeout is a defense-in-depth backstop with the same budget.
    timeout_s=10.0,
))
