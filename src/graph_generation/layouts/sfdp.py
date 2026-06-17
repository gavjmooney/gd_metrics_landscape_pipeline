"""sfdp multilevel force-directed layout (Graphviz)."""

from __future__ import annotations

import networkx as nx

from ._graphviz import parse_edge_pos, resolve_sfdp, trim_endpoint_anchors
from .base import Layout, NotApplicable, register_layout


def _sfdp(G: nx.Graph, seed: int):
    try:
        import pydot
    except ImportError as e:
        raise NotApplicable(f"pydot not available: {e}") from e
    try:
        sfdp_bin = resolve_sfdp()
    except RuntimeError as e:
        raise NotApplicable(str(e)) from e

    # sfdp uses random initial positions unless ``start=N`` is set as a
    # graph attribute. Threading the seed through start=... is what gives
    # us reproducibility for stochastic runs.
    dot = pydot.Dot(graph_type="graph", start=f"{int(seed)}")
    for n in G.nodes():
        dot.add_node(pydot.Node(str(n)))
    for u, v in G.edges():
        dot.add_edge(pydot.Edge(str(u), str(v)))

    dot_bytes = dot.create(prog=sfdp_bin, format="dot")
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
    name="sfdp", backend="graphviz", fn=_sfdp, stochastic=True,
))
