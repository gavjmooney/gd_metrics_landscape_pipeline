"""Tamassia TSM planarisation-based orthogonal layout via OGDF.

Reproducibility caveat: like FMMM (see ``fmmm.py``), this OGDF
backend exhibits cross-process nondeterminism that PYTHONHASHSEED=0
does not fully eliminate. The planarisation step picks one
combinatorial embedding from many valid choices via OGDF-internal
state we can't seed from Python; the resulting orthogonal layout
varies across subprocess invocations on the same input.
"""

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
    # 10s wall-time cap per graph. OGDF's planarisation can wedge
    # inside C++ on certain inputs (we've seen it sit at 100% CPU for
    # 10+ hours on a single corpus graph). signal.alarm can't
    # interrupt a cppyy call holding the GIL, so the hard kill in
    # _run_one's subprocess wrapper is the only reliable cap.
    timeout_s=10.0,
))
