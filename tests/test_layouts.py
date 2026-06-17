"""Registry smoke tests for the layout plugin set + node-order
independence (T4 in the reproducibility refactor).
"""

from __future__ import annotations

import io

import networkx as nx
import pytest

from graph_generation.layouts import LAYOUT_REGISTRY
from graph_generation.layouts._native import canonicalise_node_order


def test_new_layouts_registered():
    for name in ("forceatlas2", "sfdp", "drgraph"):
        assert name in LAYOUT_REGISTRY, f"{name} missing from LAYOUT_REGISTRY"


def test_new_layouts_have_callable_fn():
    for name in ("forceatlas2", "sfdp", "drgraph"):
        layout = LAYOUT_REGISTRY[name]
        assert callable(layout.fn), f"{name}.fn is not callable"


# ---- T4: layout output is graphml-node-order-independent --------------

def _round_trip_graphml(G: nx.Graph) -> nx.Graph:
    """Write G to graphml in memory, read it back. Used to mirror
    exactly what the layout stage does — so the test exercises the
    same string-typed node IDs the production code sees."""
    buf = io.BytesIO()
    nx.write_graphml(G, buf)
    buf.seek(0)
    return nx.read_graphml(buf)


def _shuffled_graphml(G: nx.Graph, key) -> nx.Graph:
    """Round-trip G through graphml with nodes inserted in the order
    given by ``sorted(..., key=key)`` — i.e. some non-canonical order.
    """
    H = G.__class__()
    H.graph.update(G.graph)
    for n in sorted(G.nodes(), key=key):
        H.add_node(n, **G.nodes[n])
    for u, v, attrs in G.edges(data=True):
        H.add_edge(u, v, **attrs)
    return _round_trip_graphml(H)


def _native_layout_names() -> list[str]:
    """Names of layouts whose backend lives entirely in Python /
    networkx / scipy — no external binaries / OGDF / cppyy. These are
    the universally-available ones the test can exercise.
    """
    out = []
    for name, lyt in LAYOUT_REGISTRY.items():
        if lyt.backend != "native":
            continue
        if name == "forceatlas2":
            try:
                import fa2_modified  # noqa: F401
            except ImportError:
                continue
        out.append(name)
    return sorted(out)


@pytest.mark.parametrize("layout_name", _native_layout_names())
def test_native_layout_node_order_independent(layout_name):
    """For every native layout, two graphmls with identical topology
    but different node order must produce identical positions after
    the canonicalisation pass."""
    if layout_name == "planar":
        # planar_layout requires a planar graph; pick one.
        G = nx.cycle_graph(8)
    elif layout_name == "curated":
        # Identity passthrough on x/y attrs — synthesise some.
        G = nx.cycle_graph(8)
        for i, n in enumerate(G.nodes()):
            G.nodes[n]["x"] = float(i)
            G.nodes[n]["y"] = float(i * 2)
    else:
        # Connected non-trivial graph that exercises the energy surface
        # of the force-directed layouts and the BFS of arc-bfs.
        G = nx.les_miserables_graph()

    # Two round-tripped copies with different node insertion orders.
    canonical_input = _round_trip_graphml(G)            # nx default order
    shuffled_input = _shuffled_graphml(G, key=lambda n: -hash(str(n)))

    layout = LAYOUT_REGISTRY[layout_name]
    seed = 12345

    pos_a, _ = layout.fn(canonicalise_node_order(canonical_input), seed)
    pos_b, _ = layout.fn(canonicalise_node_order(shuffled_input), seed)

    assert set(pos_a) == set(pos_b), (
        f"{layout_name}: position dicts cover different node sets")
    for n in pos_a:
        assert pos_a[n] == pos_b[n], (
            f"{layout_name}: node {n!r} differs after node-order shuffle: "
            f"{pos_a[n]} vs {pos_b[n]}")


def test_canonicalise_preserves_topology():
    """Sanity: canonicalisation must not lose nodes, edges, or
    attributes — only change iteration order."""
    G = nx.les_miserables_graph()
    G.nodes["Valjean"]["custom"] = 7
    H = canonicalise_node_order(G)
    assert set(H.nodes()) == set(G.nodes())
    assert set(H.edges()) == {tuple(sorted(e, key=str)) for e in G.edges()}
    assert H.nodes["Valjean"]["custom"] == 7
    # Iteration order must be sorted-by-string.
    assert list(H.nodes()) == sorted(G.nodes(), key=str)


def test_canonicalise_idempotent():
    G = canonicalise_node_order(nx.les_miserables_graph())
    H = canonicalise_node_order(G)
    assert list(H.nodes()) == list(G.nodes())
    assert list(H.edges()) == list(G.edges())
