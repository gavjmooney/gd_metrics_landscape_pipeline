"""Planar / bounded-treewidth families — random maximal planar (via
Delaunay triangulation of random 2D points) and k-trees."""

from __future__ import annotations

from typing import Any, Dict, Tuple

import networkx as nx
import numpy as np


def random_maximal_planar(n: int, rng: np.random.Generator) -> Tuple[nx.Graph, Dict[str, Any]]:
    """Uniform random points in the unit square; graph is the Delaunay
    triangulation edge set. Produces a maximal outerplanar-or-triangulation
    graph. Optionally subsamples edges to de-triangulate.

    `edge_keep_fraction` drawn from Uniform(0.5, 1.0) — 1.0 keeps the full
    triangulation, lower values thin it toward tree-like planar graphs
    while preserving planarity and (after repair) connectivity."""
    from scipy.spatial import Delaunay

    pts = rng.random(size=(n, 2))
    tri = Delaunay(pts)

    G = nx.Graph()
    G.add_nodes_from(range(n))
    for simplex in tri.simplices:
        for i in range(3):
            u, v = int(simplex[i]), int(simplex[(i + 1) % 3])
            G.add_edge(u, v)

    keep = float(rng.uniform(0.5, 1.0))
    if keep < 1.0:
        edges = list(G.edges())
        rng.shuffle(edges)
        # keep a spanning tree first so connectivity survives
        T = nx.minimum_spanning_tree(G)
        H = nx.Graph(); H.add_nodes_from(G.nodes()); H.add_edges_from(T.edges())
        extra = [e for e in edges if not H.has_edge(*e)]
        n_keep = int(round(keep * len(edges))) - H.number_of_edges()
        for e in extra[: max(0, n_keep)]:
            H.add_edge(*e)
        G = H

    return G, {"edge_keep_fraction": keep}


def k_tree(n: int, rng: np.random.Generator) -> Tuple[nx.Graph, Dict[str, Any]]:
    """A k-tree --- start with a (k+1)-clique, add each remaining node
    connected to an existing k-clique that is contained in the running
    k-tree. By construction: chordal, treewidth exactly k.
    k drawn from {2, 3} weighted 2:1.

    The registry stores k-cliques (not (k+1)-cliques): the initial
    K_{k+1} contributes k+1 such k-cliques (each (k+1)-element subset
    of size k). After attaching a new vertex v to a chosen k-clique
    C, the (k+1)-clique C ∪ {v} contributes k new k-cliques of the
    form (C \\ {x}) ∪ {v} for each x in C; the original k-clique C
    stays in the registry too."""
    k = 2 if rng.random() < 2 / 3 else 3
    if n < k + 1:
        raise ValueError(f"k-tree with k={k} needs n >= {k+1}")

    G = nx.complete_graph(k + 1)
    # Initial K_{k+1} contains k+1 distinct k-cliques (one per omitted vertex).
    initial = tuple(range(k + 1))
    cliques: list[tuple[int, ...]] = [
        tuple(initial[:i] + initial[i+1:]) for i in range(k + 1)
    ]

    for v in range(k + 1, n):
        parent = cliques[int(rng.integers(0, len(cliques)))]
        # parent is a k-clique; v gets exactly k new edges.
        for u in parent:
            G.add_edge(u, v)
        # New k-cliques formed: (parent \ {x}) ∪ {v} for each x in parent.
        for i in range(len(parent)):
            new_clique = tuple(sorted(parent[:i] + parent[i+1:] + (v,)))
            cliques.append(new_clique)

    return G, {"k": k}
