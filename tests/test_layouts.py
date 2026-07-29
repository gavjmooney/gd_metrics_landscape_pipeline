"""Registry smoke tests for the layout plugin set + node-order
independence (T4 in the reproducibility refactor).
"""

from __future__ import annotations

import io
import math
import re

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


# ---- curated edge-geometry preservation -------------------------------
#
# The graphs_with_drawings cohort must keep curator edge geometry — both
# polyline bends and cubic Béziers — from the source, through staging
# (.geg), through the curated passthrough layout (rescaled but not
# flattened), all the way to the metrics. This exercises that whole path
# on a tiny synthetic graph with one Bézier edge, one polyline edge, and
# one straight edge.

_CMD_RE = re.compile(r"[MLCQSTAVHZ]")  # uppercase SVG commands only


def _path_commands(path_str: str) -> list[str]:
    """SVG command letters in a path. Uppercase-only so the lowercase
    ``e`` of scientific-notation coordinates is never miscounted as a
    curve command."""
    return _CMD_RE.findall(path_str)


def _is_straight(path_str: str) -> bool:
    """A straight node-to-node edge is exactly one ``M`` then one ``L``."""
    return _path_commands(path_str) == ["M", "L"]


def _curated_drawing_stager(out_dir):
    """A throwaway graphs_with_drawings stager so we can drive the real
    cohort ``_write`` (GEG + geometry normalisation) without registering
    a source globally."""
    from graph_generation.sources import Source
    from graph_generation.stagers.base import Stager

    class _Drawings(Stager):  # not @register_stager — test-local only
        source_name = "_test_drawings"

        def graphs(self):
            return iter(())

    src = Source(name="_test_drawings", category="graphs_with_drawings",
                 description="", citation="")
    return _Drawings(src, out_dir)


def _synthetic_curated_graph() -> nx.Graph:
    """5 nodes; edge (0,1) a cubic Bézier bulging well clear of node 2,
    edge (1,4) a multi-L polyline, edge (2,3) a straight vertical that the
    *straight* chord of (0,1) crosses but the *curve* does not."""
    G = nx.Graph()
    for n, (x, y) in {0: (0, 0), 1: (100, 0), 2: (50, 60),
                       3: (50, -10), 4: (200, 0)}.items():
        G.add_node(n, x=float(x), y=float(y))
    G.add_edge(0, 1, path="M0,0 C20,140 80,140 100,0", polyline=True)
    G.add_edge(1, 4, path="M100,0 L150,40 L200,0", polyline=True)
    G.add_edge(2, 3)  # straight: no path attr
    return G


def test_curated_geometry_survives_staging_and_layout(tmp_path):
    import geg
    from svgpathtools import parse_path

    from graph_generation.stagers.base import StagedGraph
    from graph_generation.stages.layout import _run_one

    # --- 1. Stage through the cohort _write: file is .geg, paths intact.
    stager = _curated_drawing_stager(tmp_path)
    gid = stager._graph_id(StagedGraph(name="synth", graph=_synthetic_curated_graph()))
    assert gid.endswith(".geg"), "drawing cohort graph_id must be .geg"

    staged = tmp_path / gid
    stager._write(_synthetic_curated_graph(), staged)
    assert staged.exists()

    H = geg.read_drawing(str(staged))
    assert "C" in _path_commands(H.edges[0, 1]["path"]), \
        "Bézier edge lost its curve at staging"
    assert _path_commands(H.edges[1, 4]["path"]).count("L") >= 2, \
        "polyline edge lost its bends at staging"
    assert "path" not in H.edges[2, 3] or _is_straight(H.edges[2, 3]["path"]), \
        "straight edge should not gain geometry"

    # --- 2. Run the curated layout: rescaled, non-straight, node-attached.
    drawing = tmp_path / "curated_synth.geg"
    row = {"graph_id": gid, "category": "graphs_with_drawings",
           "source": "_test_drawings"}
    result = _run_one("curated", str(staged), str(drawing), seed=0, row=row,
                      write_drawings=True)
    assert result[1] == "ok", f"curated layout failed: {result[2]}"
    assert drawing.exists()

    D = geg.read_drawing(str(drawing))
    for u, v in [(0, 1), (1, 4)]:
        p = D.edges[u, v]["path"]
        assert not _is_straight(p), f"edge ({u},{v}) flattened to straight"
        path = parse_path(p)
        ends = (path[0].start, path[-1].end)
        centres = {(round(D.nodes[u]["x"], 6), round(D.nodes[u]["y"], 6)),
                   (round(D.nodes[v]["x"], 6), round(D.nodes[v]["y"], 6))}
        got = {(round(z.real, 6), round(z.imag, 6)) for z in ends}
        assert got == centres, (
            f"edge ({u},{v}) endpoints not snapped to rescaled node centres: "
            f"{got} vs {centres}")
    # The Bézier must still be a Bézier on disk — not re-saved as a polyline.
    assert "C" in _path_commands(D.edges[0, 1]["path"]), \
        "curve was flattened to a polyline on the rescaled drawing"

    # --- 3. Curves actually reach the metrics: curved vs forced-straight.
    straight = D.copy()
    for _, _, d in straight.edges(data=True):
        d.pop("path", None)
        d.pop("polyline", None)

    ec_c = float(geg.edge_crossings(D))
    ec_s = float(geg.edge_crossings(straight))
    neo_c = float(geg.node_edge_occlusion(D))
    neo_s = float(geg.node_edge_occlusion(straight))
    eo_c = float(geg.edge_orthogonality(D))
    eo_s = float(geg.edge_orthogonality(straight))

    # Engineered: the straight chord of (0,1) crosses (2,3); the curve
    # clears it. So crossings must differ — proving the curve geometry is
    # what the metric saw, not the straight chord.
    assert ec_c != ec_s, "edge_crossings identical — curve never reached the metric"
    assert (ec_c, neo_c, eo_c) != (ec_s, neo_s, eo_s), \
        "geometry-sensitive metrics identical between curved and straight"


def test_noncurated_layout_does_not_inherit_curator_geometry(tmp_path):
    """Regression: a non-curated layout run on a graphs_with_drawings (.geg)
    source must draw its OWN edges, never inherit the curator's path/bends.

    The cohort source is read from .geg, whose edges carry the curator's
    ``path``/``polyline`` in source coordinates. A straight-line layout
    (baur-brandes) must emit straight, node-attached edges — not the leaked
    curator curves/bends, which would corrupt the drawing and the
    path-sensitive metrics.
    """
    import geg
    from svgpathtools import parse_path

    from graph_generation.stagers.base import StagedGraph
    from graph_generation.stages.layout import _run_one
    from graph_generation.stages.metrics import edge_geometry_flags

    stager = _curated_drawing_stager(tmp_path)
    gid = stager._graph_id(StagedGraph(name="synth",
                                       graph=_synthetic_curated_graph()))
    staged = tmp_path / gid
    stager._write(_synthetic_curated_graph(), staged)
    # Precondition: the source really does carry curves + bends.
    src = geg.read_drawing(str(staged))
    src_flags = edge_geometry_flags(src)
    assert src_flags["contains_curves"] and src_flags["contains_bends"]

    drawing = tmp_path / "bb_synth.geg"
    row = {"graph_id": gid, "category": "graphs_with_drawings",
           "source": "_test_drawings"}
    result = _run_one("baur-brandes", str(staged), str(drawing), seed=0,
                      row=row, write_drawings=True)
    assert result[1] == "ok", result[2]

    D = geg.read_drawing(str(drawing))
    flags = edge_geometry_flags(D)
    assert flags["contains_curves"] is False, \
        "curator curve leaked into the baur-brandes drawing"
    assert flags["contains_bends"] is False, \
        "curator bend leaked into the baur-brandes drawing"
    # Any path present must be a straight chord on this layout's own nodes.
    for u, v, d in D.edges(data=True):
        p = d.get("path")
        if not p:
            continue
        assert _is_straight(p), f"edge ({u},{v}) is not straight: {p!r}"
        path = parse_path(p)
        ends = {(round(path[0].start.real, 3), round(path[0].start.imag, 3)),
                (round(path[-1].end.real, 3), round(path[-1].end.imag, 3))}
        centres = {(round(D.nodes[u]["x"], 3), round(D.nodes[u]["y"], 3)),
                   (round(D.nodes[v]["x"], 3), round(D.nodes[v]["y"], 3))}
        assert ends == centres, "edge endpoints not on this layout's nodes"


def _circular_crossings(G, pos) -> int:
    """Straight-chord crossings of G under circular positions ``pos``.

    Recovers the cyclic order from the angular position of each node and
    counts pairs of edges whose endpoints alternate around the circle.
    """
    order = sorted(G.nodes(), key=lambda v: math.atan2(pos[v][1], pos[v][0]))
    idx = {v: i for i, v in enumerate(order)}
    n = len(order)

    def arc(a, b, x):  # x strictly inside the clockwise arc a->b
        return 0 < (x - a) % n < (b - a) % n

    edges = list(G.edges())
    c = 0
    for i in range(len(edges)):
        a, b = edges[i]
        for j in range(i + 1, len(edges)):
            cc, dd = edges[j]
            if len({a, b, cc, dd}) < 4:
                continue
            if arc(idx[a], idx[b], idx[cc]) != arc(idx[a], idx[b], idx[dd]):
                c += 1
    return c


def test_baur_brandes_registered():
    assert "baur-brandes" in LAYOUT_REGISTRY
    assert LAYOUT_REGISTRY["baur-brandes"].backend == "native"
    assert callable(LAYOUT_REGISTRY["baur-brandes"].fn)


def test_baur_brandes_valid_circular_layout():
    G = nx.les_miserables_graph()
    pos, bends = LAYOUT_REGISTRY["baur-brandes"].fn(G, 0)
    assert bends is None
    assert set(pos) == set(G.nodes())
    # Every node distinct and on one common circle (equidistant placement).
    radii = {round(math.hypot(x, y), 6) for x, y in pos.values()}
    assert len(radii) == 1
    assert len(set(pos.values())) == G.number_of_nodes()


def test_baur_brandes_zero_crossings_on_cycle():
    # A cycle is outerplanar → circular crossing number 0; the heuristic
    # must find a crossing-free order.
    for n in (6, 9, 16, 25):
        G = nx.cycle_graph(n)
        pos, _ = LAYOUT_REGISTRY["baur-brandes"].fn(G, 0)
        assert _circular_crossings(G, pos) == 0, f"C_{n} not crossing-free"


def test_baur_brandes_reduces_crossings():
    # A 12-cycle relabelled by a coprime stride: still crossing-free under the
    # right order, but the naive id-order around the circle scrambles it.
    base = nx.cycle_graph(12)
    G = nx.relabel_nodes(base, {i: (i * 5) % 12 for i in range(12)})

    pos, _ = LAYOUT_REGISTRY["baur-brandes"].fn(G, 0)
    bb = _circular_crossings(G, pos)

    n = G.number_of_nodes()
    naive = {v: (math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n))
             for i, v in enumerate(sorted(G.nodes()))}
    naive_x = _circular_crossings(G, naive)

    assert bb == 0, f"cycle should be laid out crossing-free, got {bb}"
    assert naive_x > 0, "expected the naive order to have crossings"


def test_ensure_edge_paths_synthesises_from_bends():
    """The wikipathways path: an edge carrying intermediate ``bends`` (and no
    ``path``) must gain a synthesised polyline ``path`` so the reader / metric
    layer sees the geometry. The redundant ``bends`` attr is dropped."""
    from graph_generation.stagers.base import _ensure_edge_paths

    G = nx.Graph()
    G.add_node(0, x=0.0, y=0.0)
    G.add_node(1, x=100.0, y=0.0)
    G.add_node(2, x=50.0, y=50.0)
    G.add_edge(0, 1, bends=[(30.0, 40.0), (70.0, 40.0)])  # 2 intermediate bends
    G.add_edge(1, 2)  # straight, no bends

    _ensure_edge_paths(G)

    p = G.edges[0, 1]["path"]
    assert _path_commands(p) == ["M", "L", "L", "L"], \
        f"polyline path should be M + 3 L (u, 2 bends, v), got {p!r}"
    assert G.edges[0, 1]["polyline"] is True
    assert "bends" not in G.edges[0, 1], "redundant bends should be dropped"
    assert "30" in p and "70" in p, "bend coordinates missing from path"
    # straight edge untouched
    assert "path" not in G.edges[1, 2]


def test_gabriel_ratio_nodes_registered_and_straight_only():
    """gabriel_ratio_nodes is in the registry and is straight-by-design:
    it reads node x/y only, so adding/removing edge curvature must not
    change its value (edge geometry collapsed to the straight chord)."""
    from graph_generation.metrics import METRIC_REGISTRY, make_context

    assert "gabriel_ratio_nodes" in METRIC_REGISTRY

    G = _synthetic_curated_graph()
    straight = G.copy()
    for _, _, d in straight.edges(data=True):
        d.pop("path", None)
        d.pop("polyline", None)

    metric = METRIC_REGISTRY["gabriel_ratio_nodes"]
    v_curved = metric.fn(G, make_context(G))
    v_straight = metric.fn(straight, make_context(straight))
    assert v_curved == v_straight, \
        "gabriel_ratio_nodes must ignore edge geometry (straight-line only)"
    assert 0.0 <= v_curved <= 1.0


# ---- contains_bends / contains_curves metrics-CSV columns (task #1) ----

def _flags(*edges):
    """Build a graph from (u, v, path|None) tuples and return the flags."""
    from graph_generation.stages.metrics import edge_geometry_flags
    G = nx.Graph()
    for u, v, p in edges:
        G.add_node(u)
        G.add_node(v)
        if p is None:
            G.add_edge(u, v)
        else:
            G.add_edge(u, v, path=p)
    return edge_geometry_flags(G)


def test_edge_geometry_flags_from_paths():
    from graph_generation.stages.metrics import GEOMETRY_COLUMNS

    assert GEOMETRY_COLUMNS == ["contains_bends", "contains_curves"]

    # Straight chords (no path, or single M+L) → neither flag.
    assert _flags((0, 1, None)) == {"contains_bends": False,
                                    "contains_curves": False}
    assert _flags((0, 1, "M0,0 L10,10")) == {"contains_bends": False,
                                             "contains_curves": False}

    # Polyline with an interior vertex (>= 2 line commands) → bend only.
    f = _flags((0, 1, "M0,0 L5,5 L10,0"))
    assert f["contains_bends"] and not f["contains_curves"]

    # Cubic Bézier → curve only (one straight segment doesn't make a bend).
    f = _flags((0, 1, "M0,0 C2,8 8,8 10,0"))
    assert f["contains_curves"] and not f["contains_bends"]
    # A leading straight segment then a curve is still curve-only (1 L).
    f = _flags((0, 1, "M0,0 L5,5 C6,8 9,8 10,0"))
    assert f["contains_curves"] and not f["contains_bends"]

    # Both: two line segments AND a curve in one path.
    f = _flags((0, 1, "M0,0 L5,5 L8,3 C9,4 9,2 10,0"))
    assert f["contains_bends"] and f["contains_curves"]

    # OR across edges: one bent edge + one curved edge → both flags.
    f = _flags((0, 1, "M0,0 L5,5 L10,0"), (1, 2, "M10,0 C12,8 18,8 20,0"))
    assert f["contains_bends"] and f["contains_curves"]

    # Scientific-notation coordinates must NOT be read as commands — the
    # 'e'/'E' exponent is the classic false positive we must avoid.
    f = _flags((0, 1, "M1.5e-3,2.0E1 L3e2,4e0"))
    assert f == {"contains_bends": False, "contains_curves": False}, \
        "sci-notation exponent miscounted as a command"


def test_compute_in_memory_appends_geometry_flags():
    """compute_in_memory must append the geometry flags (so both CSV
    producers emit them) without timing them as metrics."""
    from graph_generation.stages.metrics import (
        compute_in_memory, GEOMETRY_COLUMNS)

    G = _synthetic_curated_graph()  # has a Bézier edge AND a polyline edge
    vals, timings = compute_in_memory(G, ["edge_crossings"])

    for col in GEOMETRY_COLUMNS:
        assert col in vals, f"{col} missing from metric values"
        assert col not in timings, f"{col} should not be timed as a metric"
    assert vals["contains_curves"] is True
    assert vals["contains_bends"] is True
