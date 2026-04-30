"""Equidistant circular layout."""

from __future__ import annotations

import networkx as nx

from ._native import to_pos_dict
from .base import Layout, register_layout


def _circular(G: nx.Graph, seed: int):
    return to_pos_dict(nx.circular_layout(G)), None


LAYOUT = register_layout(Layout(
    name="circular", backend="native", fn=_circular, stochastic=False,
))
