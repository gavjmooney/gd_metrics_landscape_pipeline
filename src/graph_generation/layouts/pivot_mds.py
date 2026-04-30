"""Pivot-MDS (Brandes & Pich 2006) landmark MDS via OGDF."""

from __future__ import annotations

import networkx as nx

from ._ogdf import extract_positions, import_ogdf, to_ogdf
from .base import Layout, register_layout


def _pivot_mds(G: nx.Graph, seed: int):
    ogdf, cppinclude = import_ogdf()
    cppinclude("ogdf/energybased/PivotMDS.h")

    G_ogdf, GA, _, rev = to_ogdf(G)
    mds = ogdf.PivotMDS()
    mds.call(GA)
    return extract_positions(GA, rev), None


LAYOUT = register_layout(Layout(
    name="pivot-MDS", backend="ogdf", fn=_pivot_mds, stochastic=False,
))
