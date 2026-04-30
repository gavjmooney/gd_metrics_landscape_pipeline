"""FMMM (Hachul & Junger 2004) multilevel force-directed via OGDF."""

from __future__ import annotations

import networkx as nx

from ._ogdf import extract_positions, import_ogdf, to_ogdf
from .base import Layout, register_layout


def _fmmm(G: nx.Graph, seed: int):
    ogdf, cppinclude = import_ogdf()
    cppinclude("ogdf/energybased/FMMMLayout.h")

    G_ogdf, GA, _, rev = to_ogdf(G)
    fm = ogdf.FMMMLayout()
    fm.useHighLevelOptions(True)
    fm.unitEdgeLength(30.0)
    fm.newInitialPlacement(True)
    fm.qualityVersusSpeed(ogdf.FMMMOptions.QualityVsSpeed.GorgeousAndEfficient)
    fm.randSeed(seed)
    fm.call(GA)
    return extract_positions(GA, rev), None


LAYOUT = register_layout(Layout(
    name="FMMM", backend="ogdf", fn=_fmmm, stochastic=True,
))
