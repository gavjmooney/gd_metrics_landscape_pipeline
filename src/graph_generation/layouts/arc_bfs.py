"""Arc diagram with BFS-ordered axis layout (curved bends)."""

from __future__ import annotations

import math

import networkx as nx

from .base import Layout, register_layout

_ARC_BENDS = 8


def _arc_bfs(G: nx.Graph, seed: int):
    start = min(G.nodes(), key=lambda n: (G.degree(n), n))
    order = list(nx.bfs_tree(G, start).nodes())
    remaining = [n for n in G.nodes() if n not in set(order)]
    order += remaining

    positions = {order[i]: (float(i), 0.0) for i in range(len(order))}

    bends = {}
    for u, v in G.edges():
        xu, xv = positions[u][0], positions[v][0]
        cx = (xu + xv) / 2.0
        r = abs(xv - xu) / 2.0
        if r == 0.0:
            continue
        pts = []
        for k in range(1, _ARC_BENDS + 1):
            t = k / (_ARC_BENDS + 1)
            theta = math.pi * t
            pts.append((cx - r * math.cos(theta), r * math.sin(theta)))
        if xu > xv:
            pts.reverse()
        bends[(u, v)] = pts
    return positions, bends


LAYOUT = register_layout(Layout(
    name="arc-bfs", backend="native", fn=_arc_bfs, stochastic=False,
))
