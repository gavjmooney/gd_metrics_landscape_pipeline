"""Helpers for native (networkx / numpy / scipy) layouts."""

from __future__ import annotations

from typing import Mapping

import networkx as nx

from .base import Positions


def to_pos_dict(pos: Mapping) -> Positions:
    return {n: (float(xy[0]), float(xy[1])) for n, xy in pos.items()}


def canonicalise_node_order(G: nx.Graph) -> nx.Graph:
    """Return a copy of ``G`` whose nodes are inserted in sorted-by-
    string order.

    NetworkX iterates nodes in insertion order. graphml on disk
    therefore encodes node order, and any layout that depends on
    iteration order (every native layout, plus the OGDF / Graphviz
    bridges that build their own graph by iterating ``G.nodes()`` and
    ``G.edges()``) inherits whatever order the file was written in.

    Two graphmls with the same topology but different node order would
    then yield different layouts, even for "deterministic" algorithms
    (kamada-kawai, spectral, planar, ...). This helper rebuilds ``G``
    with a canonical node order so the layout output is a function of
    topology, not file order. Node identities are preserved exactly;
    only the iteration order changes.

    Edges are inserted in sorted ``(min, max)`` order under the new
    node order. Node and edge attributes are copied through unchanged.
    """
    sorted_nodes = sorted(G.nodes(), key=str)
    H = G.__class__()
    H.graph.update(G.graph)
    for n in sorted_nodes:
        H.add_node(n, **G.nodes[n])
    # Sort edges by string-keyed endpoints so iteration is also stable.
    if H.is_directed():
        edge_iter = sorted(G.edges(data=True),
                           key=lambda e: (str(e[0]), str(e[1])))
    else:
        edge_iter = sorted(
            ((u, v, d) if str(u) <= str(v) else (v, u, d)
             for u, v, d in G.edges(data=True)),
            key=lambda e: (str(e[0]), str(e[1])),
        )
    for u, v, attrs in edge_iter:
        H.add_edge(u, v, **attrs)
    return H
