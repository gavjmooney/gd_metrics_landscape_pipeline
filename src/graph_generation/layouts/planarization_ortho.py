"""Tamassia TSM planarisation-based orthogonal layout via OGDF."""

from __future__ import annotations

import networkx as nx

from ._ogdf import extract_bends, extract_positions, import_ogdf, to_ogdf
from .base import Layout, register_layout


def _planarization_ortho(G: nx.Graph, seed: int):
    ogdf, cppinclude = import_ogdf()
    cppinclude("ogdf/planarity/PlanarizationLayout.h")
    cppinclude("ogdf/orthogonal/OrthoLayout.h")

    G_ogdf, GA, _, rev = to_ogdf(G)
    pl = ogdf.PlanarizationLayout()
    pl.call(GA, G_ogdf)
    return extract_positions(GA, rev), extract_bends(GA, G_ogdf, rev)


LAYOUT = register_layout(Layout(
    name="planarization-ortho", backend="ogdf",
    fn=_planarization_ortho, stochastic=False,
))
