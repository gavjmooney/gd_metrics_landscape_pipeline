"""Named graph families with analytically-known layout properties.

Calibration anchors: graphs whose optimal metric values or structural
lower / upper bounds are known from graph-drawing theory. They let us
check the layout + metric pipeline against ground truth and witness
structurally-forced coverage gaps without relying on rejection sampling.

Unlike the random cohort, calibration graphs are deterministic — no
seed. Each has a stable family name and `params_json = {"family": NAME}`.
The density cap **does not apply** — K_n and other dense anchors are
intentionally included.
"""

from __future__ import annotations

from typing import Callable, List, Tuple

import networkx as nx


def _to_int_labels(G: nx.Graph) -> nx.Graph:
    return nx.convert_node_labels_to_integers(G)


def catalogue(n_max: int = 75) -> List[Tuple[str, nx.Graph]]:
    """Return `(family_name, graph)` for every calibration graph with
    `n_nodes <= n_max`. Graphs are returned with integer node labels
    and no attributes (ready for graphml serialisation)."""

    e: List[Tuple[str, Callable[[], nx.Graph]]] = []

    # Complete graphs K_n — all non-planar for n >= 5, known crossing
    # numbers: cr(K_5)=1, cr(K_6)=3, cr(K_7)=9, cr(K_8)=18, ...
    for n in range(5, 11):
        e.append((f"K_{n}", lambda n=n: nx.complete_graph(n)))

    # Complete bipartite K_{p,q} — cr(K_{3,3})=1, cr(K_{4,4})=4, cr(K_{5,5})=16
    kpq_pairs = [(2, 3), (2, 4), (2, 5), (2, 7), (3, 3), (3, 4), (3, 5),
                 (3, 7), (4, 4), (4, 5), (4, 6), (4, 7), (5, 5), (5, 6),
                 (5, 7), (6, 6)]
    for p, q in kpq_pairs:
        e.append((f"K_{p}_{q}", lambda p=p, q=q: nx.complete_bipartite_graph(p, q)))

    # Named sporadic graphs with known properties
    e.append(("petersen", nx.petersen_graph))             # n=10, cr=2, 3-regular
    e.append(("heawood", nx.heawood_graph))               # n=14, bipartite 3-regular
    e.append(("pappus", nx.pappus_graph))                 # n=18, bipartite 3-regular
    e.append(("desargues", nx.desargues_graph))           # n=20, bipartite 3-regular
    e.append(("dodecahedral", nx.dodecahedral_graph))     # n=20, 3-regular planar
    e.append(("truncated_tetrahedron", nx.truncated_tetrahedron_graph))
    e.append(("truncated_cube", nx.truncated_cube_graph))
    e.append(("octahedral", nx.octahedral_graph))

    # Cycles — 2-regular, AR ceiling = π, all bipartite when n even
    for n in [5, 6, 7, 10, 15, 20, 30, 50, 75]:
        e.append((f"C_{n}", lambda n=n: nx.cycle_graph(n)))

    # Paths — trees, bipartite, AR varies by endpoint handling
    for n in [5, 10, 20, 50, 75]:
        e.append((f"P_{n}", lambda n=n: nx.path_graph(n)))

    # Stars K_{1,k} — max-degree k, AR ceiling 2π/k (classical bound)
    # nx.star_graph(k) returns K_{1,k} with k+1 nodes
    for k in [5, 10, 20, 40, 60]:
        e.append((f"star_{k}", lambda k=k: nx.star_graph(k)))

    # Wheels W_k — k spokes + hub = k+1 nodes, hub has degree k
    for k in [5, 7, 10, 15, 20, 30]:
        e.append((f"W_{k}", lambda k=k: nx.wheel_graph(k)))

    # Balanced binary trees (branching factor 2, height h) — 2^(h+1)-1 nodes
    for h in [3, 4, 5, 6]:
        e.append((f"bin_tree_h{h}", lambda h=h: nx.balanced_tree(2, h)))

    # 2D grids m × k
    grid_shapes = [(3, 3), (3, 4), (4, 4), (4, 5), (5, 5), (3, 6), (4, 6),
                   (5, 6), (6, 6), (3, 7), (4, 7), (5, 7), (6, 7), (7, 7),
                   (5, 8), (6, 8), (3, 10), (4, 10), (5, 10), (6, 10),
                   (5, 12), (5, 15)]
    for m, k in grid_shapes:
        e.append((f"grid_{m}x{k}",
                  lambda m=m, k=k: _to_int_labels(nx.grid_2d_graph(m, k))))

    # Hypercubes Q_d — 2^d nodes, d-regular, bipartite
    for d in [3, 4, 5, 6]:
        e.append((f"Q_{d}", lambda d=d: _to_int_labels(nx.hypercube_graph(d))))

    # Materialise, strip attrs, filter to n <= n_max
    out: List[Tuple[str, nx.Graph]] = []
    for name, ctor in e:
        G = ctor()
        if G.number_of_nodes() > n_max:
            continue
        G = _to_int_labels(G) if isinstance(list(G.nodes())[0], tuple) else G
        # strip any attrs the NetworkX constructors may leave
        G.graph.clear()
        for _, attrs in G.nodes(data=True):
            attrs.clear()
        for _, _, attrs in G.edges(data=True):
            attrs.clear()
        out.append((name, G))
    return out
