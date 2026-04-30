"""Kamada-Kawai energy-minimisation layout."""

from __future__ import annotations

import networkx as nx

from ._native import to_pos_dict
from .base import Layout, register_layout


def _kamada_kawai(G: nx.Graph, seed: int):
    return to_pos_dict(nx.kamada_kawai_layout(G)), None


LAYOUT = register_layout(Layout(
    name="kamada-kawai", backend="native",
    fn=_kamada_kawai, stochastic=False,
))
