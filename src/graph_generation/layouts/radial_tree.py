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


def _manifest_is_tree(row) -> bool:
    """Manifest-side pre-filter: row["is_tree"] is True.

    The manifest stores the result of ``nx.is_tree`` for every graph
    (computed once at staging). Reading the column lets the dispatcher
    skip non-tree graphs without paying the per-graph graphml load +
    re-check that would otherwise cost ~20 minutes on a 90k-row corpus.
    """
    v = row.get("is_tree")
    return v is True or str(v).strip().lower() == "true"


LAYOUT = register_layout(Layout(
    name="radial-tree", backend="ogdf", fn=_radial_tree, stochastic=False,
    applies_to=lambda G: nx.is_tree(G),
    manifest_applies_to=_manifest_is_tree,
))
