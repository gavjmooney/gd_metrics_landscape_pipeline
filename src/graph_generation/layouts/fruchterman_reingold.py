"""Fruchterman-Reingold spring embedder (networkx ``spring_layout``)."""

from __future__ import annotations

import networkx as nx

from ._native import to_pos_dict
from .base import Layout, register_layout


def _fruchterman_reingold(G: nx.Graph, seed: int):
    return to_pos_dict(nx.spring_layout(G, seed=seed)), None


LAYOUT = register_layout(Layout(
    name="fruchterman-reingold", backend="native",
    fn=_fruchterman_reingold, stochastic=True,
))
