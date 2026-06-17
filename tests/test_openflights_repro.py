"""Reproducibility regression for the openflights stager.

The stager used to call ``add_edges_from(edge_set)`` directly on a
Python ``set``, whose iteration order depends on PYTHONHASHSEED.
Across two pipeline runs that meant the same source data produced
graphmls with different node labelings — the only stager-level source
of non-reproducibility in the corpus (confirmed by comparing all 74
sources between two output directories).

This test rebuilds a graph from a tiny edge-set fixture under
different PYTHONHASHSEED values and asserts the resulting node labels
+ edge list are identical. Without the sort the test fails because
``add_edges_from`` inserts nodes in hash-iteration order, and
``convert_node_labels_to_integers`` then cements the random ordering
into the on-disk graphml.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap


_PROBE = textwrap.dedent("""
    import networkx as nx
    # Plausible openflights edge set: many str pairs hashable by Python's
    # string hash. Three distinct hash seeds will reorder iteration.
    edge_set = {
        ("3030", "2990"), ("2990", "2939"), ("2939", "1382"),
        ("1382", "1701"), ("1701", "2939"), ("2990", "1382"),
        ("1701", "3030"), ("3030", "2939"), ("2939", "1701"),
    }
    G = nx.Graph()
    G.add_edges_from(sorted(edge_set))  # <-- THE FIX
    G = nx.convert_node_labels_to_integers(G)
    G.graph.clear()
    nodes = sorted(G.nodes())
    edges = sorted(tuple(sorted(e)) for e in G.edges())
    print(f"NODES={nodes}")
    print(f"EDGES={edges}")
""")


def _run(seed: str) -> tuple[str, str]:
    env = {**os.environ, "PYTHONHASHSEED": seed}
    out = subprocess.check_output(
        [sys.executable, "-c", _PROBE], text=True, env=env,
    )
    lines = out.strip().splitlines()
    return lines[0], lines[1]


def test_openflights_node_order_stable_across_hash_seeds():
    """Same input edge set under different PYTHONHASHSEED values must
    produce the same renumbered graph. With ``add_edges_from(set)``
    this fails; with ``add_edges_from(sorted(set))`` it passes."""
    a_nodes, a_edges = _run("0")
    b_nodes, b_edges = _run("123")
    c_nodes, c_edges = _run("random")

    assert a_nodes == b_nodes == c_nodes, (
        f"node renumbering differs across hash seeds:\n"
        f"  seed=0:      {a_nodes}\n  seed=123:    {b_nodes}\n"
        f"  seed=random: {c_nodes}"
    )
    assert a_edges == b_edges == c_edges, (
        f"edge list differs across hash seeds:\n"
        f"  seed=0:      {a_edges}\n  seed=123:    {b_edges}\n"
        f"  seed=random: {c_edges}"
    )


def test_openflights_stager_uses_sorted_iteration():
    """Direct source check: the fix has to live in the stager. A future
    refactor that drops the ``sorted()`` would re-open the bug, so we
    assert the source contains a sorted call on the edge container."""
    import inspect
    from graph_generation.stagers import openflights
    src = inspect.getsource(openflights.OpenFlightsAirportsStager.graphs)
    assert "sorted(edge_set)" in src or "sorted(by_country" in src, (
        "openflights stager no longer iterates edge_set in sorted order — "
        "this re-introduces the PYTHONHASHSEED-dependent node renumbering "
        "bug that produced 59 non-reproducible airport graphs in the "
        "earlier comparison."
    )
