"""Thin wrapper around geg's property computation.

Drops fields that are constant-by-construction for the generated cohort
(is_directed, is_multigraph, n_self_loops, n_connected_components,
is_connected, is_dag) so the manifest isn't padded with constants.

Adds two derived structural ceilings / floors that aren't in geg:
- `crossing_number_lb_euler` — Euler's bound, a lower bound on cr(G)
- `crossing_number_lb_bipartite` — tighter bound for bipartite graphs

These lower bounds are the analytic EC-ceiling witnesses: they pin the
structural infeasibility of drawing the graph with few crossings,
independent of any layout algorithm's performance.
"""

from __future__ import annotations

from typing import Any, Dict

import networkx as nx

from geg.graph_properties import compute_properties


_CONSTANT_BY_CONSTRUCTION = {
    "is_directed",
    "is_multigraph",
    "n_self_loops",
    "n_connected_components",
    "is_connected",
    "is_dag",
}


def crossing_number_lb_euler(G: nx.Graph) -> int:
    """Euler's bound on crossing number. Simple planar graphs with
    n ≥ 3 satisfy m ≤ 3n − 6. Any excess is a forced crossings lower
    bound: cr(G) ≥ m − (3n − 6). Returns 0 for planar-feasible cases."""
    n, m = G.number_of_nodes(), G.number_of_edges()
    if n < 3:
        return 0
    return max(0, m - (3 * n - 6))


def crossing_number_lb_bipartite(G: nx.Graph) -> float:
    """Tighter Euler bound for bipartite graphs: m ≤ 2n − 4 for
    n ≥ 3. NaN when the graph isn't bipartite (the generic Euler bound
    in `crossing_number_lb_euler` applies instead)."""
    if not nx.is_bipartite(G):
        return float("nan")
    n, m = G.number_of_nodes(), G.number_of_edges()
    if n < 3:
        return 0
    return max(0, m - (2 * n - 4))


def compute(G: nx.Graph) -> Dict[str, Any]:
    """Compute all manifest properties for a validated graph."""
    props = compute_properties(G)
    props = {k: v for k, v in props.items() if k not in _CONSTANT_BY_CONSTRUCTION}
    props["crossing_number_lb_euler"] = crossing_number_lb_euler(G)
    props["crossing_number_lb_bipartite"] = crossing_number_lb_bipartite(G)
    return props


MANIFEST_PROPERTY_ORDER = [
    "n_nodes", "n_edges", "density",
    "is_bipartite", "is_planar", "is_tree", "is_forest",
    "is_regular", "is_eulerian",
    "min_degree", "max_degree", "mean_degree", "degree_std",
    "diameter", "radius", "avg_shortest_path_length",
    "n_triangles", "average_clustering", "transitivity",
    "degree_assortativity",
    "n_biconnected_components", "degeneracy",
    "crossing_number_lb_euler", "crossing_number_lb_bipartite",
]
