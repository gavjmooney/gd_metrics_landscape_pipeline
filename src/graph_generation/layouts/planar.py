"""Schnyder planar embedding (only defined for planar graphs)."""

from __future__ import annotations

import networkx as nx

from ._native import to_pos_dict
from .base import Layout, NotApplicable, register_layout


def _planar(G: nx.Graph, seed: int):
    is_planar, _ = nx.check_planarity(G)
    if not is_planar:
        raise NotApplicable("graph is non-planar")
    return to_pos_dict(nx.planar_layout(G)), None


LAYOUT = register_layout(Layout(
    name="planar", backend="native", fn=_planar, stochastic=False,
    applies_to=lambda G: nx.is_planar(G),
))
