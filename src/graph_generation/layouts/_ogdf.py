"""Helpers for OGDF-backed layouts via ``ogdf-python`` cppyy bindings."""

from __future__ import annotations

from typing import Dict, List, Tuple

import networkx as nx

from .base import Bends, NotApplicable, Positions


def import_ogdf():
    try:
        from ogdf_python import ogdf, cppinclude
    except ImportError as e:
        raise NotApplicable(
            f"OGDF backend not available; install ogdf-python ({e})"
        ) from e
    return ogdf, cppinclude


def to_ogdf(G: nx.Graph):
    ogdf, cppinclude = import_ogdf()
    cppinclude("ogdf/basic/Graph.h")
    cppinclude("ogdf/basic/GraphAttributes.h")

    G_ogdf = ogdf.Graph()
    GA = ogdf.GraphAttributes(
        G_ogdf,
        ogdf.GraphAttributes.nodeGraphics
        | ogdf.GraphAttributes.edgeGraphics
        | ogdf.GraphAttributes.nodeLabel,
    )
    node_map: Dict = {}
    rev: Dict = {}
    for nid in G.nodes():
        v = G_ogdf.newNode()
        node_map[nid] = v
        rev[v] = nid
        GA.width[v] = 20.0
        GA.height[v] = 20.0
    for u, v in G.edges():
        G_ogdf.newEdge(node_map[u], node_map[v])
    return G_ogdf, GA, node_map, rev


def extract_positions(GA, rev_node_map) -> Positions:
    return {nid: (float(GA.x[v]), float(GA.y[v]))
            for v, nid in rev_node_map.items()}


def extract_bends(GA, G_ogdf, rev_node_map) -> Bends:
    bends: Bends = {}
    for e in G_ogdf.edges:
        pl = GA.bends[e]
        pts: List[Tuple[float, float]] = [
            (float(p.m_x), float(p.m_y)) for p in pl
        ]
        if pts:
            u_nid = rev_node_map[e.source()]
            v_nid = rev_node_map[e.target()]
            bends[(u_nid, v_nid)] = pts
    return bends
