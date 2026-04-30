"""Reingold-Tilford radial tree layout via OGDF (trees only)."""

from __future__ import annotations

import networkx as nx

from ._ogdf import extract_positions, import_ogdf, to_ogdf
from .base import Layout, NotApplicable, register_layout


def _radial_tree(G: nx.Graph, seed: int):
    if not nx.is_tree(G):
        raise NotApplicable("graph is not a tree")
    ogdf, cppinclude = import_ogdf()
    cppinclude("ogdf/tree/RadialTreeLayout.h")

    G_ogdf, GA, _, rev = to_ogdf(G)
    rt = ogdf.RadialTreeLayout()
    rt.call(GA)
    return extract_positions(GA, rev), None


LAYOUT = register_layout(Layout(
    name="radial-tree", backend="ogdf", fn=_radial_tree, stochastic=False,
    applies_to=lambda G: nx.is_tree(G),
))
