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

When ``return_timings=True``, :func:`compute` also returns per-property
wall-clock timings — used by the stage runners to write a sidecar
``_timings/properties.csv`` for empirical-vs-theoretical complexity
analysis.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Tuple

import networkx as nx

from geg import graph_properties as gp
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


def compute(G: nx.Graph, return_timings: bool = False
            ) -> Dict[str, Any] | Tuple[Dict[str, Any], Dict[str, float]]:
    """Compute all manifest properties for a validated graph.

    With the default ``return_timings=False`` the call returns the
    properties dict (back-compat with every existing caller). With
    ``return_timings=True`` it returns ``(values, timings_in_seconds)``
    where ``timings`` is a dict from property name to wall-clock
    seconds — captured per-property so the stage runners can dump a
    sidecar CSV for complexity analysis.
    """
    if not return_timings:
        return _compute_values(G)

    return _compute_with_timings(G)


def _compute_values(G: nx.Graph) -> Dict[str, Any]:
    props = compute_properties(G)
    props = {k: v for k, v in props.items() if k not in _CONSTANT_BY_CONSTRUCTION}
    props["crossing_number_lb_euler"] = crossing_number_lb_euler(G)
    props["crossing_number_lb_bipartite"] = crossing_number_lb_bipartite(G)
    return props


def _compute_with_timings(G: nx.Graph
                           ) -> Tuple[Dict[str, Any], Dict[str, float]]:
    """Replicate :func:`geg.graph_properties.compute_properties` but time
    each property individually.

    The body mirrors geg's loop in ``compute_properties`` (call each
    name in ``PROPERTY_NAMES``, NaN on exception) so the values stay
    byte-identical to the un-timed path. The two extra
    ``crossing_number_lb_*`` we used to add here are already in
    ``PROPERTY_NAMES`` upstream, so they fall out for free.
    """
    values: Dict[str, Any] = {}
    timings: Dict[str, float] = {}
    for name in gp.PROPERTY_NAMES:
        if name in _CONSTANT_BY_CONSTRUCTION:
            continue
        fn = getattr(gp, name)
        t0 = time.perf_counter()
        try:
            if name in gp._APSP_DEPENDENT:
                values[name] = fn(G, apsp=None, weight=None)
            else:
                values[name] = fn(G)
        except Exception:
            values[name] = float("nan")
        timings[name] = time.perf_counter() - t0
    return values, timings


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
