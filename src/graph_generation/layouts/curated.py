"""Passthrough 'layout' over curator-supplied positions.

Graphs in the ``graphs_with_drawings`` cohort already carry ``x`` / ``y``
attributes from whoever drew them (Pajek vlad, gd_collection_v1
hand-laid samples, COIL-DEL embeddings, etc.). We want metric coverage
under those original positions alongside the algorithmic layouts —
every other Layout overwrites x/y with its own computed coordinates,
so the curator's drawing would otherwise vanish from the corpus.

This pseudo-layout is identity for node positions: it reads the existing
x/y, returns them unchanged, and lets the standard ``_run_one`` path apply
the canonical rescale + metric pass. ``applies_to`` returns True only
when every node has x and y, so the layout naturally short-circuits
to ``n/a`` on the synthetic / external cohorts that don't have
curator drawings.

**Edge geometry is preserved, not dropped.** Curator drawings in the
``graphs_with_drawings`` cohort carry real edge routing — polyline bends
and cubic Béziers — stored on disk as ``.geg`` (SVG ``path`` strings).
The identity layout returns ``bends=None`` because the standard
``standardise(positions, bends)`` channel only models polyline bends and
cannot round-trip curves. Instead the layout stage (``stages/layout.py``)
captures the source ``path`` strings, transforms them with the same
node-derived affine that ``rescale.standardise`` applies, and re-attaches
them via :func:`rescale_paths` so the saved drawing keeps the curator's
exact curved edges locked to the rescaled nodes. See :func:`rescale_paths`
and :func:`transform_path` below.
"""

from __future__ import annotations

import networkx as nx

from .base import Layout, register_layout


def _has_curator_positions(G: nx.Graph) -> bool:
    if G.number_of_nodes() == 0:
        return False
    for _, attrs in G.nodes(data=True):
        if "x" not in attrs or "y" not in attrs:
            return False
    return True


def _curated(G: nx.Graph, seed: int):
    positions = {
        n: (float(attrs["x"]), float(attrs["y"]))
        for n, attrs in G.nodes(data=True)
    }
    # Identity for node positions. Edge geometry (curved/polyline `path`s
    # loaded from the source `.geg`) is NOT returned through `bends` — that
    # channel can only encode polyline bends and would flatten Béziers. The
    # layout stage instead transforms the source `path`s with the same
    # node-derived affine and re-attaches them (see `rescale_paths`), so the
    # curator's exact edges survive to the metrics and the saved drawing.
    return positions, None


def transform_path(path_str: str, cx: float, cy: float, scale: float) -> str:
    """Apply the affine ``(x, y) -> ((x - cx) * scale, (y - cy) * scale)`` to
    every coordinate in an SVG path ``d`` string.

    Uses ``svgpathtools`` so command structure and curve control points are
    transformed geometrically: a uniform scale + translation maps a cubic
    Bézier to a cubic Bézier (control points transform with the curve), so
    no fidelity is lost. Command letters (M/L/C/Q/S/T/A/H/V/Z) are preserved.
    """
    from svgpathtools import parse_path
    p = parse_path(path_str)
    # translate by (-cx, -cy) then uniform-scale about the origin.
    p = p.translated(complex(-cx, -cy)).scaled(scale)
    return p.d()


def rescale_paths(G: nx.Graph, geometry, cx: float, cy: float,
                  scale: float) -> None:
    """Re-attach curator edge geometry to ``G`` in the rescaled node frame.

    ``geometry`` maps ``(u, v) -> (source_path, polyline_flag)``, captured in
    the *source* coordinate frame before the rescale. Each path is transformed
    by the node-derived affine ``(cx, cy, scale)`` (see
    :func:`graph_generation.rescale.standardise_params`) and snapped so its
    endpoints sit exactly on the rescaled node centres. The result is stored
    back on the edge as ``path`` (+ the original ``polyline`` flag) so both the
    in-memory metric pass and the ``.geg`` write see the curved geometry.

    Curves are preserved exactly — never flattened to polyline bends, which
    would re-save Béziers as polylines on disk.
    """
    from geg._paths import snap_path_to_endpoints
    for (u, v), (src_path, poly) in geometry.items():
        if not G.has_edge(u, v):
            continue
        try:
            transformed = transform_path(src_path, cx, cy, scale)
        except Exception:
            # Unparseable source path — leave the edge straight rather than
            # sink the whole drawing.
            continue
        if u in G.nodes and v in G.nodes:
            u_xy = (G.nodes[u]["x"], G.nodes[u]["y"])
            v_xy = (G.nodes[v]["x"], G.nodes[v]["y"])
            try:
                transformed = snap_path_to_endpoints(transformed, u_xy, v_xy)
            except Exception:
                pass
        G.edges[u, v]["path"] = transformed
        G.edges[u, v]["polyline"] = poly


def _manifest_is_drawing_cohort(row) -> bool:
    """Manifest-side pre-filter: only ``graphs_with_drawings`` carry
    curator x/y attributes.

    Topology cohorts (``generated``, ``calibration``, ``real_world``,
    ``benchmark``) write minimal graphml with no node attrs — the
    runtime ``_has_curator_positions`` check on those is guaranteed to
    return False, so we skip them without ever loading the file.
    Saves ~80k graphml loads on a 90k-row corpus.
    """
    return str(row.get("category", "")) == "graphs_with_drawings"


LAYOUT = register_layout(Layout(
    name="curated", backend="curated",
    fn=_curated, stochastic=False,
    applies_to=_has_curator_positions,
    manifest_applies_to=_manifest_is_drawing_cohort,
))
