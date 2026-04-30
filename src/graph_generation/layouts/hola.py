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
))
