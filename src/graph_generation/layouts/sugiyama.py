"""Sugiyama hierarchical layered drawing via OGDF."""

from __future__ import annotations

import networkx as nx

from ._ogdf import extract_bends, extract_positions, import_ogdf, to_ogdf
from .base import Layout, register_layout


def _sugiyama(G: nx.Graph, seed: int):
    ogdf, cppinclude = import_ogdf()
    cppinclude("ogdf/layered/SugiyamaLayout.h")

    G_ogdf, GA, _, rev = to_ogdf(G)
    sl = ogdf.SugiyamaLayout()
    sl.call(GA)
    return extract_positions(GA, rev), extract_bends(GA, G_ogdf, rev)


LAYOUT = register_layout(Layout(
    name="sugiyama", backend="ogdf", fn=_sugiyama, stochastic=False,
))
