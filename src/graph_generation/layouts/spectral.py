"""Laplacian spectral embedding."""

from __future__ import annotations

import networkx as nx

from ._native import to_pos_dict
from .base import Layout, register_layout


def _spectral(G: nx.Graph, seed: int):
    return to_pos_dict(nx.spectral_layout(G)), None


LAYOUT = register_layout(Layout(
    name="spectral", backend="native", fn=_spectral, stochastic=False,
))
