"""Hierarchical dot layout with ``splines=ortho`` orthogonal routing."""

from __future__ import annotations

import networkx as nx

from ._graphviz import parse_edge_pos, resolve_dot, trim_endpoint_anchors
from .base import Layout, NotApplicable, register_layout


def _dot_ortho(G: nx.Graph, seed: int):
    try:
        import pydot
    except ImportError as e:
        raise NotApplicable(f"pydot not available: {e}") from e
    try:
        dot_bin = resolve_dot()
    except RuntimeError as e:
        raise NotApplicable(str(e)) from e

    dot = pydot.Dot(graph_type="graph", splines="ortho")
    for n in G.nodes():
        dot.add_node(pydot.Node(str(n)))
    for u, v in G.edges():
        dot.add_edge(pydot.Edge(str(u), str(v)))

    dot_bytes = dot.create(prog=dot_bin, format="dot")
    parsed = pydot.graph_from_dot_data(dot_bytes.decode("utf-8"))[0]

    name_map = {str(n): n for n in G.nodes()}

    positions = {}
    for node in parsed.get_nodes():
        name = node.get_name().strip('"')
        if name in {"node", "edge", "graph"}:
            continue
        pos = node.get_pos()
        if not pos:
            continue
        x, y = pos.strip('"').split(",")
        positions[name_map.get(name, name)] = (float(x), float(y))

    bends = {}
    for edge in parsed.get_edges():
        u = name_map.get(edge.get_source().strip('"'))
        v = name_map.get(edge.get_destination().strip('"'))
        pos = edge.get_pos()
        if not pos:
            continue
        pts = parse_edge_pos(pos.strip('"'))
        pts = trim_endpoint_anchors(pts, positions.get(u), positions.get(v))
        if pts:
            bends[(u, v)] = pts

    return positions, bends


LAYOUT = register_layout(Layout(
    name="dot-ortho", backend="graphviz", fn=_dot_ortho, stochastic=False,
))
