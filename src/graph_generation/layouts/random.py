"""Uniform random positions baseline."""

from __future__ import annotations

import networkx as nx

from ._native import to_pos_dict
from .base import Layout, register_layout


def _random(G: nx.Graph, seed: int):
    return to_pos_dict(nx.random_layout(G, seed=seed)), None


LAYOUT = register_layout(Layout(
    name="random", backend="native", fn=_random, stochastic=True,
))
