"""Hand-rolled Sankey-like pipeline diagram (no Plotly / d3-sankey).

Plotly's Sankey enforces strict flow conservation per node, which we
fought against because the manifest (~89K graphs) fans out into 19
layouts and ~1.5M drawings. To make the upstream cohort columns
visually comparable to the downstream drawing/metric columns, the flow
unit upstream of the deduped corpus is ``(graph, layout) pairs``: each
graph contributes N_LAYOUTS pair-units. The deduped → layout column
transitions back to raw drawing counts, sized proportionally per
layout (planar / radial-tree / HOLA / curated and the timeout-prone
algorithms produce fewer drawings because they don't apply to or
finish for every graph).

Counts load from ``analysis/data/sankey_overview.json``, produced by
``analysis/rebuild_sankey_overview.py``. Re-run that script after a
pipeline run to refresh the numbers.

Usage:
    pip install svglib reportlab
    python sankey_pipeline.py
    # writes sankey_pipeline.{svg,pdf} to analysis/figs/.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Load pipeline counts from the JSON sidecar.
# ---------------------------------------------------------------------------

JSON_PATH = Path(__file__).resolve().parent / "data" / "sankey_overview.json"
_SUMMARY = json.loads(JSON_PATH.read_text(encoding="utf-8"))

# Cohort key in JSON → display name shown on the figure.
COHORT_DISPLAY = {
    "generated":            "Generated",
    "calibration":          "Calibration",
    "benchmark":            "Benchmark",
    "real_world":           "Real world",
    "graphs_with_drawings": "Graphs with drawings",
}

# Sub-source pretty names — JSON-key → display label. Anything not in
# the dict passes through verbatim, so unknown sources still render.
SUBSOURCE_DISPLAY = {
    # Generated — algorithmic families
    "planar_max":   "Planar (max)",
    "k_tree":       "k-tree",
    "bba":          "BBA",
    "tree_uniform": "Uniform tree",
    "nws":          "NWS",
    "er":           "Erdos-Renyi",
    "sbm":          "SBM",
    "hrg":          "HRG",
    "caterpillar":  "Caterpillar",
    "k_regular":    "k-regular",
    "geo":          "Geometric",
    "lfr":          "LFR",
    # Calibration
    "exhaustive_small": "Exhaustive (n<=7)",
    "calibration":      "Canonical",
    # Benchmark
    "rome":       "Rome",
    "north":      "North",
    "random-dag": "Random DAG",
    # Real world (after collapse)
    "TUDataset":            "TUDataset",
    "houseofgraphs":        "House of Graphs",
    "netzschleuder":        "Netzschleuder",
    "openflights_airports": "OpenFlights airports",
    "ieee_pes":             "IEEE PES",
    "suitesparse_small":    "SuiteSparse",
    # Graphs with drawings
    "gd_collection_v1": "GD collection",
    "wikipathways":     "WikiPathways",
    "ndex":             "NDEx",
    "pajek":            "Pajek",
}

# Layout pretty names.
LAYOUT_DISPLAY = {
    "FMMM":                 "FMMM",
    "arc-bfs":              "Arc-BFS",
    "circular":             "Circular",
    "dot-ortho":            "Dot orthogonal",
    "drgraph":              "DRGraph",
    "forceatlas2":          "ForceAtlas2",
    "kamada-kawai":         "Kamada-Kawai",
    "fruchterman-reingold": "Fruchterman-Reingold",
    "stress-majorization":  "Stress majorization",
    "pivot-MDS":            "Pivot MDS",
    "sfdp":                 "sfdp",
    "sugiyama":             "Sugiyama",
    "random":               "Random",
    "spectral":             "Spectral",
    "planarization-ortho":  "Planarization orthogonal",
    "planar":               "Planar",
    "HOLA":                 "HOLA",
    "curated":              "Curated",
    "radial-tree":          "Radial tree",
}

# Readability metric pretty names.
METRIC_DISPLAY = {
    "angular_resolution":        "Angular resolution",
    "aspect_ratio":              "Aspect ratio",
    "crossing_angle":            "Crossing angle",
    "edge_crossings":            "Edge crossings",
    "edge_length_deviation":     "Edge length deviation",
    "edge_orthogonality":        "Edge orthogonality",
    "kruskal_stress":            "Kruskal stress",
    "neighbourhood_preservation":"Neighbourhood preservation",
    "node_edge_occlusion":       "Node-edge occlusion",
    "node_resolution":           "Node resolution",
    "node_uniformity":           "Node uniformity",
}

# Graph property pretty names.
PROPERTY_DISPLAY = {
    "n_nodes":                       "Nodes",
    "n_edges":                       "Edges",
    "density":                       "Density",
    "is_bipartite":                  "Bipartite",
    "is_planar":                     "Planar",
    "is_tree":                       "Tree",
    "is_forest":                     "Forest",
    "is_regular":                    "Regular",
    "is_eulerian":                   "Eulerian",
    "min_degree":                    "Min degree",
    "max_degree":                    "Max degree",
    "mean_degree":                   "Mean degree",
    "degree_std":                    "Degree std.",
    "diameter":                      "Diameter",
    "radius":                        "Radius",
    "avg_shortest_path_length":      "Avg. shortest path length",
    "n_triangles":                   "Triangles",
    "average_clustering":            "Average clustering",
    "transitivity":                  "Transitivity",
    "degree_assortativity":          "Degree assortativity",
    "n_biconnected_components":      "Biconnected components",
    "degeneracy":                    "Degeneracy",
    "crossing_number_lb_euler":      "Crossing number LB (Euler)",
    "crossing_number_lb_bipartite":  "Crossing number LB (bipartite)",
}

# "Staged" = post-stage / pre-sample manifest snapshot. Per-cohort and
# per-(cohort, sub-source) breakdowns come from the pre-sample backup
# captured under `pre_sample_manifest`.
_PRESAMPLE = _SUMMARY["pre_sample_manifest"]

COHORT_STAGED: Dict[str, int] = {
    COHORT_DISPLAY[c]: n
    for c, n in sorted(
        _PRESAMPLE["per_cohort"].items(),
        key=lambda kv: list(COHORT_DISPLAY).index(kv[0]),
    )
}

# In our pipeline filtering happens *inside* the stage step (out_of_size,
# disconnected, density-cap, no-edges), so there is no separate
# "staged → filtered" reduction. Keep the column slot but pass through
# unchanged; LOSS_FILTER == 0 suppresses the discard link.
TOTAL_STAGED   = _PRESAMPLE["total"]
TOTAL_FILTERED = TOTAL_STAGED
TOTAL_SAMPLED  = _SUMMARY["stages"]["sample"]["after"]
TOTAL_DEDUPED  = _SUMMARY["stages"]["dedup"]["after"]

# Layouts: order by descending drawing count so the dense bars cluster
# at the top of the column.
LAYOUT_DRAWINGS: Dict[str, int] = dict(
    sorted(
        _SUMMARY["drawings"]["per_layout"].items(),
        key=lambda kv: -kv[1],
    )
)
N_LAYOUTS = len(LAYOUT_DRAWINGS)
TOTAL_DRAWINGS = _SUMMARY["drawings"]["total"]


# Readability metrics computed per drawing. Every drawing produces a
# value for every metric, so the all_drawings → metrics fan-out is
# asymmetric: out-flow = N_METRICS × in-flow. The layout function
# normalizes per-side (sum of in-links / sum of out-links) rather than
# by a single node value, which is what makes this asymmetry render
# correctly.
METRIC_NAMES = list(_SUMMARY["metrics"])
N_METRICS = len(METRIC_NAMES)


# Graph properties computed per graph at promotion. Constant along the
# pipeline (graph-level), so shown as a "ladder" strip below the deduped
# corpus column rather than as flow nodes. Hard-coded — properties don't
# appear in the JSON because they flow at graph level, not as Sankey arcs.
PROPERTY_NAMES = [
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


# Sub-source breakdown per cohort, derived from the pre-sample manifest
# so each cohort's sub-sources sum exactly to COHORT_STAGED[cohort]. For
# Generated and Calibration the manifest's `source` field is empty, so
# `00_overview.py` falls back to the `generator` column — that's why
# Generated splits into 12 algorithmic families and Calibration splits
# into exhaustive_small / calibration.
SUBSOURCE_STAGED: Dict[str, Dict[str, int]] = {
    cohort: {} for cohort in COHORT_STAGED
}
for entry in _PRESAMPLE["per_cohort_source"]:
    cohort = COHORT_DISPLAY[entry["category"]]
    # Collapse nested sources by their main-source prefix: e.g. all
    # TUDataset/<sub> entries roll up to "TUDataset", netzschleuder/<sub>
    # to "netzschleuder". Bare names (rome, houseofgraphs, ...) pass
    # through. Stops the Real-world column from overflowing with ~60
    # individual TUDataset variants.
    main = entry["source"].split("/", 1)[0]
    label = SUBSOURCE_DISPLAY.get(main, main)
    SUBSOURCE_STAGED[cohort][label] = (
        SUBSOURCE_STAGED[cohort].get(label, 0) + entry["count"]
    )
SUBSOURCE_STAGED = {
    cohort: dict(sorted(parts.items(), key=lambda kv: -kv[1]))
    for cohort, parts in SUBSOURCE_STAGED.items()
}


# ---------------------------------------------------------------------------
# Pair-unit counts (multiply graph counts by N_LAYOUTS for the reductive side)
# ---------------------------------------------------------------------------

PAIR_FACTOR = N_LAYOUTS

COHORT_PAIRS  = {c: n * PAIR_FACTOR for c, n in COHORT_STAGED.items()}
PAIRS_STAGED  = TOTAL_STAGED  * PAIR_FACTOR
PAIRS_SAMPLED = TOTAL_SAMPLED * PAIR_FACTOR
PAIRS_DEDUPED = TOTAL_DEDUPED * PAIR_FACTOR

# Per-reason discard counts. Filter losses happened *during* the stage
# step (out_of_size, disconnected, density-cap, no_edges); for the
# diagram they're shown as a parallel discard reason alongside sample
# and dedup. Sum of stage filter_totals from the JSON. The staged node
# accepts asymmetric in/out (in = cohort sum at the post-filter count;
# out = filter + sample + dedup + admitted at the raw count), and the
# renderer's per-side normalization fills both bar sides cleanly.
TOTAL_FILTER_LOSS = sum(_SUMMARY["stages"]["stage"]["filter_totals"].values())
LOSS_FILTER = TOTAL_FILTER_LOSS * PAIR_FACTOR
LOSS_SAMPLE = (TOTAL_STAGED  - TOTAL_SAMPLED)  * PAIR_FACTOR
LOSS_DEDUP  = (TOTAL_SAMPLED - TOTAL_DEDUPED)  * PAIR_FACTOR
PAIRS_DISCARD = LOSS_FILTER + LOSS_SAMPLE + LOSS_DEDUP


# ---------------------------------------------------------------------------
# Visual style.
# ---------------------------------------------------------------------------

STAGE = {
    "source":       "#6c8ebf",
    "filter":       "#d6a647",
    "sample":       "#e08a4f",
    "dedup":        "#c66e5e",
    "layout":       "#82b485",
    "aggregate":    "#9d7ab5",
    "metric":       "#5c8b9b",
    "notapplicable":"#bbb09a",
    "discarded":    "#d0d0d0",
    "property":     "#7a8d8a",
}


def _rgba(hex_colour: str, alpha: float) -> str:
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# Visual scale: sqrt compresses the dynamic range so the multiplied
# upstream stages don't dwarf everything. The labels keep the actual
# counts (graphs upstream, drawings downstream).
def visual(value: float) -> float:
    return math.sqrt(max(value, 0))


# ---------------------------------------------------------------------------
# Diagram structures.
# ---------------------------------------------------------------------------

@dataclass
class Node:
    id: str
    label: str
    sublabel: str
    column: int
    value: float          # for height computation
    colour: str
    y_centre: float       # 0..1 (target vertical centre)
    height: float = 0.0   # px, computed
    x: float = 0.0        # px, computed (left edge)
    y_top: float = 0.0    # px, computed
    in_links: List["Link"] = field(default_factory=list)
    out_links: List["Link"] = field(default_factory=list)


@dataclass
class Link:
    source: str
    target: str
    value: float          # pair count
    colour: str
    label: str = ""
    # computed band positions
    src_y0: float = 0.0
    src_y1: float = 0.0
    tgt_y0: float = 0.0
    tgt_y1: float = 0.0


# ---------------------------------------------------------------------------
# Build node + link list.
# ---------------------------------------------------------------------------

def build_graph() -> Tuple[Dict[str, Node], List[Link]]:
    nodes: Dict[str, Node] = {}

    # Column 1 — cohort sources
    cohort_y = {
        "Generated":            0.18,
        "Calibration":          0.30,
        "Benchmark":            0.42,
        "Real world":           0.62,
        "Graphs with drawings": 0.88,
    }
    for c in COHORT_STAGED:
        nodes[c] = Node(
            id=c, label=c, sublabel=f"{COHORT_STAGED[c]:,}",
            column=1, value=COHORT_PAIRS[c], colour=STAGE["source"],
            y_centre=cohort_y[c],
        )

    # Column 0 — sub-sources (generation algorithms / dataset sources).
    # y_centre is set to the parent cohort's y_centre with a tiny
    # incremental offset per sub-source, so the layout sweep stacks them
    # in declaration order under their cohort without crossings.
    for cohort, parts in SUBSOURCE_STAGED.items():
        base_y = cohort_y[cohort]
        for i, (sub_name, sub_count) in enumerate(parts.items()):
            offset = (i - (len(parts) - 1) / 2) * 0.0005
            nodes[f"sub::{cohort}::{sub_name}"] = Node(
                id=f"sub::{cohort}::{sub_name}",
                label=sub_name, sublabel=f"{sub_count:,}",
                column=0, value=sub_count * PAIR_FACTOR,
                colour=STAGE["source"], y_centre=base_y + offset,
            )

    # Columns 2..4 — reductive stages. We omit a separate "filtered"
    # column because in our pipeline filtering happens *inside* the
    # stage step (out_of_size, disconnected, density-cap, no-edges) —
    # what we call "staged" is already post-filter.
    nodes["staged"]   = Node("staged",   "Staged graph set", f"{TOTAL_STAGED:,}",
                               column=2, value=PAIRS_STAGED,   colour=STAGE["source"],
                               y_centre=0.45)

    # Column 3 — admitted + three discard-reason intermediate nodes.
    # Staged splits four ways: one stream survives to become Admitted
    # (the layout input), the other three are the named discard reasons.
    # Filter losses happened *during* the stage step but are surfaced
    # here as a parallel reason so all three drop categories appear at
    # the same depth in the figure. Each reason node then forwards into
    # the single Discarded sink in col 4 — making the three reasons
    # readable while keeping a single end-state node for "everything
    # that didn't make it".
    nodes["admitted"]  = Node("admitted",  "Admitted graphs", f"{TOTAL_DEDUPED:,}",
                                column=3, value=PAIRS_DEDUPED,  colour=STAGE["layout"],
                                y_centre=0.20)
    nodes["filter_out"] = Node("filter_out", "Filter out", f"{TOTAL_FILTER_LOSS:,}",
                                column=3, value=LOSS_FILTER, colour=STAGE["filter"],
                                y_centre=0.55)
    nodes["sample_out"] = Node("sample_out", "Sample out", f"{TOTAL_STAGED - TOTAL_SAMPLED:,}",
                                column=3, value=LOSS_SAMPLE, colour=STAGE["sample"],
                                y_centre=0.72)
    nodes["dedup_out"]  = Node("dedup_out",  "Dedup out",  f"{TOTAL_SAMPLED - TOTAL_DEDUPED:,}",
                                column=3, value=LOSS_DEDUP,  colour=STAGE["dedup"],
                                y_centre=0.88)

    # Column 4 — single Discarded sink that aggregates the three
    # reason streams.
    discarded_total = TOTAL_FILTER_LOSS + (TOTAL_STAGED - TOTAL_SAMPLED) + (TOTAL_SAMPLED - TOTAL_DEDUPED)
    nodes["discard"] = Node("discard", "Discarded graphs", f"{discarded_total:,}",
                              column=4, value=PAIRS_DISCARD, colour=STAGE["discarded"],
                              y_centre=0.70)

    # Column 5 — individual layouts. Bar height is proportional to the
    # number of drawings that layout actually produced (not all 16
    # layouts apply to every graph: planar / radial-tree / HOLA / curated
    # are sparse).
    for i, (name, drawings_n) in enumerate(LAYOUT_DRAWINGS.items()):
        nodes[f"layout::{name}"] = Node(
            id=f"layout::{name}", label=LAYOUT_DISPLAY.get(name, name),
            sublabel=f"{drawings_n:,}",
            column=5, value=drawings_n * PAIR_FACTOR,
            colour=STAGE["layout"], y_centre=(i + 0.5) / N_LAYOUTS,
        )

    # Column 6 — aggregate sink for all successful drawings. Drawings
    # are *not* persisted to disk in the actual pipeline (apart from a
    # ~5/source verify sample): the layout step computes positions and
    # streams them straight into the metric calculators in the same
    # process.
    nodes["all_drawings"] = Node(
        "all_drawings", "All drawings", f"{TOTAL_DRAWINGS:,}",
        column=6, value=TOTAL_DRAWINGS, colour=STAGE["aggregate"],
        y_centre=0.50,
    )

    # Column 7 — readability metrics (one per metric). Every drawing
    # contributes one value to every metric, so this fans out: each
    # metric receives the FULL all_drawings count. Fan-out is rendered
    # asymmetrically by the per-side normalization in `layout()`.
    for i, mname in enumerate(METRIC_NAMES):
        nodes[f"metric::{mname}"] = Node(
            id=f"metric::{mname}", label=METRIC_DISPLAY.get(mname, mname),
            sublabel=f"{TOTAL_DRAWINGS:,}",
            column=7, value=TOTAL_DRAWINGS, colour=STAGE["metric"],
            y_centre=(i + 0.5) / N_METRICS,
        )

    links: List[Link] = []
    # sub-source -> cohort
    for cohort, parts in SUBSOURCE_STAGED.items():
        for sub_name, sub_count in parts.items():
            links.append(Link(
                f"sub::{cohort}::{sub_name}", cohort,
                sub_count * PAIR_FACTOR, _rgba(STAGE["source"], 0.45),
            ))

    # cohort -> staged
    for c in COHORT_STAGED:
        links.append(Link(c, "staged", COHORT_PAIRS[c], _rgba(STAGE["source"], 0.45)))

    # staged -> 4-way fan: admitted (the survivors) + 3 discard reasons.
    # The staged node accepts asymmetric in/out: in-side carries the
    # cohort sum at the post-filter count (PAIRS_STAGED), out-side
    # carries the four-way split which sums to (PAIRS_STAGED + LOSS_FILTER)
    # because filter losses happened *upstream* of the staged count.
    # Per-side normalization in `layout()` makes both sides fill the bar.
    links.append(Link("staged", "admitted", PAIRS_DEDUPED,
                      _rgba(STAGE["layout"], 0.55)))
    if LOSS_FILTER > 0:
        links.append(Link("staged", "filter_out", LOSS_FILTER,
                          _rgba(STAGE["filter"], 0.55)))
    if LOSS_SAMPLE > 0:
        links.append(Link("staged", "sample_out", LOSS_SAMPLE,
                          _rgba(STAGE["sample"], 0.55)))
    if LOSS_DEDUP > 0:
        links.append(Link("staged", "dedup_out", LOSS_DEDUP,
                          _rgba(STAGE["dedup"], 0.55)))

    # Each reason -> Discarded sink.
    for reason_id, loss_val, reason_colour in [
        ("filter_out", LOSS_FILTER, STAGE["filter"]),
        ("sample_out", LOSS_SAMPLE, STAGE["sample"]),
        ("dedup_out",  LOSS_DEDUP,  STAGE["dedup"]),
    ]:
        if loss_val > 0:
            links.append(Link(reason_id, "discard", loss_val,
                              _rgba(reason_colour, 0.5)))

    # admitted -> each layout. Link width is proportional to the number
    # of drawings that layout actually produced. Sum of out-flows
    # (TOTAL_DRAWINGS) is smaller than the admitted node's in-flow
    # (PAIRS_DEDUPED); the per-side normalization in `layout()` makes
    # both bar sides fill, with the asymmetry hidden.
    for name, n_drawings in LAYOUT_DRAWINGS.items():
        links.append(Link("admitted", f"layout::{name}",
                          n_drawings * PAIR_FACTOR,
                          _rgba(STAGE["layout"], 0.4)))

    # each layout -> all_drawings (raw drawing count, not pair-units —
    # this is where we transition out of the pair-unit regime).
    for name, n_drawings in LAYOUT_DRAWINGS.items():
        links.append(Link(f"layout::{name}", "all_drawings", n_drawings,
                          _rgba(STAGE["aggregate"], 0.35)))

    # all_drawings -> each metric. Every drawing produces a value for
    # every metric, so each link carries TOTAL_DRAWINGS — the
    # all_drawings node's out-side total is N_METRICS × in-side total.
    for mname in METRIC_NAMES:
        links.append(Link("all_drawings", f"metric::{mname}",
                          TOTAL_DRAWINGS, _rgba(STAGE["metric"], 0.35)))

    # populate node link refs
    for lk in links:
        nodes[lk.source].out_links.append(lk)
        nodes[lk.target].in_links.append(lk)

    return nodes, links


# ---------------------------------------------------------------------------
# Layout: assign node x/y/heights and link band positions.
# ---------------------------------------------------------------------------

def layout(nodes: Dict[str, Node], links: List[Link],
           *, width: float, height: float,
           margin: float = 6.0, node_w: float = 12.0,
           label_pad_left: float = 150.0, label_pad_right: float = 260.0,
           header_pad: float = 120.0, footer_pad: float = 0.0,
           x_positions: List[float] = None) -> None:
    # x_positions span 0..1 within the inner plot area; label_pad_left
    # and label_pad_right reserve space outside that area for the
    # leftmost (right-anchored) and rightmost (left-anchored) text labels
    # so they don't get clipped by the SVG edge. header_pad reserves
    # space at the top of the canvas for column headers; footer_pad
    # reserves space at the bottom for the property-ladder strip.
    # Column 1 (cohorts) puts labels into the col-1 → col-2 gap, which
    # is wider than the others to fit names like "Graphs-w-drawings".
    if x_positions is None:
        x_positions = [0.0, 0.06, 0.18, 0.32, 0.44, 0.58, 0.74, 1.0]
    top = margin + header_pad
    bottom = margin + footer_pad
    cols: Dict[int, List[Node]] = {}
    for n in nodes.values():
        cols.setdefault(n.column, []).append(n)

    # Visual scale: each node's height = sqrt(value) * scale. Each link's
    # width on the source side = link_value / sqrt(source.value), and on
    # the target side = link_value / sqrt(target.value). With this rule,
    # the sum of link widths at each node side exactly equals the node's
    # visual height — every node fills both sides.
    col_visual_total = {c: sum(visual(n.value) for n in col_nodes)
                        for c, col_nodes in cols.items()}

    # Pads are constant in pixels and not scaled. Pick the scale that
    # makes the most-crowded column fit exactly. Column 0 (sub-sources)
    # holds 28 stacked labels; if its bars get too thin the labels
    # overlap, so it gets a larger pad to guarantee a per-row stride
    # at least as tall as a 9pt text line.
    PAD_DEFAULT = 6.0
    # Col 0: 28 stacked sub-source labels need 9pt-line spacing.
    # Col 7: 11 metric rows, single-line labels — modest stride keeps
    #        them clearly separated without overflowing the canvas.
    PAD_OVERRIDES = {0: 15.0, 7: 14.0}

    def _pad_for(col_id: int) -> float:
        return PAD_OVERRIDES.get(col_id, PAD_DEFAULT)

    budget = height - top - bottom
    scales = []
    for c, col_nodes in cols.items():
        pad_total = (len(col_nodes) - 1) * _pad_for(c)
        v = col_visual_total[c]
        if v > 0:
            scales.append((budget - pad_total) / v)
    scale = min(scales) if scales else 1.0

    # Assign node pixel heights and x positions
    plot_width = width - label_pad_left - label_pad_right
    for n in nodes.values():
        n.height = visual(n.value) * scale
        n.x = label_pad_left + x_positions[n.column] * plot_width

    # Place nodes vertically within each column. Use the user-provided
    # y_centre as a hint, then resolve overlaps by sweeping top-to-bottom.
    for col_id, col_nodes in cols.items():
        # sort by y_centre
        col_nodes.sort(key=lambda n: n.y_centre)
        # initial y_top from y_centre
        for n in col_nodes:
            n.y_top = top + n.y_centre * budget - n.height / 2

        col_pad = _pad_for(col_id)
        # sweep down to fix overlaps (preserve relative order)
        for i in range(1, len(col_nodes)):
            prev = col_nodes[i - 1]
            cur = col_nodes[i]
            min_top = prev.y_top + prev.height + col_pad
            if cur.y_top < min_top:
                cur.y_top = min_top
        # check that we don't overflow bottom; if so, sweep up
        last = col_nodes[-1]
        col_bottom = last.y_top + last.height
        if col_bottom > height - bottom:
            shift = col_bottom - (height - bottom)
            # try to push all up uniformly
            for n in col_nodes:
                n.y_top -= shift
            # then sweep up to fix any top overflow
            for i in range(len(col_nodes) - 2, -1, -1):
                cur = col_nodes[i]
                nxt = col_nodes[i + 1]
                max_top = nxt.y_top - cur.height - col_pad
                if cur.y_top > max_top:
                    cur.y_top = max_top
            # ensure first isn't above the top header pad
            first = col_nodes[0]
            if first.y_top < top:
                shift = top - first.y_top
                for n in col_nodes:
                    n.y_top += shift

    # Distribute link bands at each node's edges. The width of an out-
    # link on the source side = (link.value / sum_of_out_link_values) *
    # source.height; the width of an in-link on the target side =
    # (link.value / sum_of_in_link_values) * target.height. Each side
    # is normalized independently, so the bar fills 100% on both sides
    # even when in-flow and out-flow totals differ — required for
    # asymmetric fan-outs like all_drawings → 11 metrics, where every
    # drawing produces every metric and out-total = N_METRICS × in-total.
    for n in nodes.values():
        out_total = sum(lk.value for lk in n.out_links)
        in_total  = sum(lk.value for lk in n.in_links)
        # Outgoing: sort by target y_top
        n.out_links.sort(key=lambda l: nodes[l.target].y_top)
        cursor = n.y_top
        for lk in n.out_links:
            band = (lk.value / out_total) * n.height if out_total > 0 else 0
            lk.src_y0 = cursor
            lk.src_y1 = cursor + band
            cursor += band
        # Incoming: sort by source y_top
        n.in_links.sort(key=lambda l: nodes[l.source].y_top)
        cursor = n.y_top
        for lk in n.in_links:
            band = (lk.value / in_total) * n.height if in_total > 0 else 0
            lk.tgt_y0 = cursor
            lk.tgt_y1 = cursor + band
            cursor += band


# ---------------------------------------------------------------------------
# SVG emission.
# ---------------------------------------------------------------------------

def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def link_path(x0: float, y0_top: float, y0_bot: float,
              x1: float, y1_top: float, y1_bot: float) -> str:
    # Cubic bezier band: top edge from (x0, y0_top) to (x1, y1_top);
    # bottom edge from (x1, y1_bot) to (x0, y0_bot); closed.
    cx = (x0 + x1) / 2
    return (
        f"M{x0:.2f},{y0_top:.2f} "
        f"C{cx:.2f},{y0_top:.2f} {cx:.2f},{y1_top:.2f} {x1:.2f},{y1_top:.2f} "
        f"L{x1:.2f},{y1_bot:.2f} "
        f"C{cx:.2f},{y1_bot:.2f} {cx:.2f},{y0_bot:.2f} {x0:.2f},{y0_bot:.2f} "
        f"Z"
    )


def render_svg(nodes: Dict[str, Node], links: List[Link],
               width: float, height: float, node_w: float = 12.0,
               footer_pad: float = 0.0) -> str:
    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" font-family="Helvetica,Arial,sans-serif">'
    )
    # Background
    parts.append(f'<rect width="{width}" height="{height}" fill="white"/>')


    # Column headers — single-column titles for the layout and metric
    # columns, plus span titles that group the blue source columns and
    # the orange-red processing columns.
    column_headers = {5: "Layout algorithms", 7: "Readability metrics"}
    for col_id, htext in column_headers.items():
        col_nodes = [n for n in nodes.values() if n.column == col_id]
        if col_nodes:
            header_x = col_nodes[0].x + node_w / 2
            parts.append(
                f'<text x="{header_x:.2f}" y="30" text-anchor="middle" '
                f'dominant-baseline="alphabetic" font-size="16" '
                f'font-weight="bold">{_esc(htext)}</text>'
            )

    span_headers = [
        (0, 2, "Graph sources"),
        (3, 4, "Graph processing"),
    ]
    for left_col, right_col, htext in span_headers:
        left_nodes = [n for n in nodes.values() if n.column == left_col]
        right_nodes = [n for n in nodes.values() if n.column == right_col]
        if left_nodes and right_nodes:
            x_left = left_nodes[0].x
            x_right = right_nodes[0].x + node_w
            header_x = (x_left + x_right) / 2
            parts.append(
                f'<text x="{header_x:.2f}" y="30" text-anchor="middle" '
                f'dominant-baseline="alphabetic" font-size="16" '
                f'font-weight="bold">{_esc(htext)}</text>'
            )

    # Process labels — describe what each section does. Section-centered
    # labels sit directly beneath their section header (spanning the
    # whole section); gap-positioned labels describe within-section
    # transitions and sit in the column gap they apply to. Two-line
    # labels split on '\n'.
    section_process_labels = [
        (0, 2, "Download, filter, compute properties\n(filters: n <= 75, density cap by n, connected, simple)"),
        (3, 4, "Stratified sample (per-source caps),\nthen cross-source dedup (24-property tuple)"),
        (5, 5, f"Compute {N_LAYOUTS - 1} layouts + curated"),
        (7, 7, f"Compute {N_METRICS} metrics per drawing"),
    ]
    gap_process_labels: list = []

    def _emit_process_label(x: float, ptext: str) -> None:
        for i, line in enumerate(ptext.split("\n")):
            parts.append(
                f'<text x="{x:.2f}" y="{56 + i * 16:.2f}" '
                f'text-anchor="middle" dominant-baseline="alphabetic" '
                f'font-size="13" font-style="italic" fill="#333">'
                f'{_esc(line)}</text>'
            )

    for left_col, right_col, ptext in section_process_labels:
        left_nodes = [n for n in nodes.values() if n.column == left_col]
        right_nodes = [n for n in nodes.values() if n.column == right_col]
        if left_nodes and right_nodes:
            cx = (left_nodes[0].x + right_nodes[0].x + node_w) / 2
            _emit_process_label(cx, ptext)

    for left_col, right_col, ptext in gap_process_labels:
        left_nodes = [n for n in nodes.values() if n.column == left_col]
        right_nodes = [n for n in nodes.values() if n.column == right_col]
        if left_nodes and right_nodes:
            gap_x = (left_nodes[0].x + node_w + right_nodes[0].x) / 2
            _emit_process_label(gap_x, ptext)

    # Links first (so nodes draw on top)
    for lk in links:
        src = nodes[lk.source]; tgt = nodes[lk.target]
        x0 = src.x + node_w
        x1 = tgt.x
        path = link_path(x0, lk.src_y0, lk.src_y1,
                         x1, lk.tgt_y0, lk.tgt_y1)
        parts.append(f'<path d="{path}" fill="{lk.colour}" stroke="none"/>')

    # Nodes
    for n in nodes.values():
        parts.append(
            f'<rect x="{n.x:.2f}" y="{n.y_top:.2f}" '
            f'width="{node_w}" height="{n.height:.2f}" '
            f'fill="{n.colour}" stroke="black" stroke-width="0.4"/>'
        )
        # Label position: outside the node, on the side that has more space.
        # For first column put labels to the LEFT; rightmost column put
        # labels to the RIGHT; intermediate columns put labels above the
        # node. Use small font.
        cx_node = n.x + node_w / 2
        cy_node = n.y_top + n.height / 2
        if n.column == 0:
            # sub-sources: name + count on a single line, anchored end
            # left of the bar (extends into label_pad_left).
            tx = n.x - 4
            ty = cy_node
            parts.append(
                f'<text x="{tx:.2f}" y="{ty:.2f}" text-anchor="end" '
                f'dominant-baseline="middle" font-size="13">'
                f'{_esc(n.label)} <tspan fill="#444" font-size="12">'
                f'{_esc(n.sublabel)}</tspan></text>'
            )
        elif n.column == 1:
            # cohorts: bold label + count to the RIGHT of the bar,
            # anchored start (extends into the col-1 → col-2 gap and
            # crosses link bands, so we paint a white plate behind it).
            tx = n.x + node_w + 4
            ty = cy_node
            bg_w = max(len(n.label), len(n.sublabel)) * 7 + 4
            parts.append(
                f'<rect x="{tx - 2:.2f}" y="{ty - 9:.2f}" '
                f'width="{bg_w:.2f}" height="35" '
                f'fill="white" stroke="none" opacity="0.94"/>'
            )
            parts.append(
                f'<text x="{tx:.2f}" y="{ty:.2f}" text-anchor="start" '
                f'dominant-baseline="middle" font-size="14" font-weight="bold">'
                f'{_esc(n.label)}</text>'
            )
            parts.append(
                f'<text x="{tx:.2f}" y="{ty + 16:.2f}" text-anchor="start" '
                f'dominant-baseline="middle" font-size="13" fill="#333">'
                f'{_esc(n.sublabel)}</text>'
            )
        elif n.column == 6:
            # aggregate sink (all_drawings): bold label + count to the
            # right of the bar; the col-6 → col-7 fan crosses this
            # space, so a white plate keeps it readable.
            tx = n.x + node_w + 4
            ty = cy_node
            bg_w = max(len(n.label), len(n.sublabel)) * 7 + 4
            parts.append(
                f'<rect x="{tx - 2:.2f}" y="{ty - 9:.2f}" '
                f'width="{bg_w:.2f}" height="35" '
                f'fill="white" stroke="none" opacity="0.94"/>'
            )
            parts.append(
                f'<text x="{tx:.2f}" y="{ty:.2f}" text-anchor="start" '
                f'dominant-baseline="middle" font-size="14" font-weight="bold">'
                f'{_esc(n.label)}</text>'
            )
            parts.append(
                f'<text x="{tx:.2f}" y="{ty + 16:.2f}" text-anchor="start" '
                f'dominant-baseline="middle" font-size="13" fill="#333">'
                f'{_esc(n.sublabel)}</text>'
            )
        elif n.column == 7:
            # readability metrics: single-line metric name + count
            # (count is identical for every metric = TOTAL_DRAWINGS).
            tx = n.x + node_w + 4
            ty = cy_node
            parts.append(
                f'<text x="{tx:.2f}" y="{ty:.2f}" text-anchor="start" '
                f'dominant-baseline="middle" font-size="13">'
                f'{_esc(n.label)} <tspan fill="#444" font-size="12">'
                f'{_esc(n.sublabel)}</tspan></text>'
            )
        elif n.column == 5:
            # individual layouts: name + drawing count, single line.
            # Sits over the col-5 → col-6 link bands, so we paint a
            # white plate behind it for legibility.
            tx = n.x + node_w + 3
            ty = cy_node
            bg_w = (len(n.label) + 1 + len(n.sublabel)) * 7.0 + 4
            parts.append(
                f'<rect x="{tx - 2:.2f}" y="{ty - 9:.2f}" '
                f'width="{bg_w:.2f}" height="18" '
                f'fill="white" stroke="none" opacity="0.94"/>'
            )
            parts.append(
                f'<text x="{tx:.2f}" y="{ty:.2f}" text-anchor="start" '
                f'dominant-baseline="middle" font-size="13">'
                f'{_esc(n.label)} <tspan fill="#444" font-size="12">'
                f'{_esc(n.sublabel)}</tspan></text>'
            )
        else:
            # reductive stages: bold label above the bar, count below
            tx = cx_node
            ty = n.y_top - 4
            parts.append(
                f'<text x="{tx:.2f}" y="{ty:.2f}" text-anchor="middle" '
                f'dominant-baseline="alphabetic" font-size="14" font-weight="bold">'
                f'{_esc(n.label)}</text>'
            )
            parts.append(
                f'<text x="{tx:.2f}" y="{n.y_top + n.height + 11:.2f}" '
                f'text-anchor="middle" font-size="13" fill="#333">'
                f'{_esc(n.sublabel)}</text>'
            )


    parts.append('</svg>')
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    # Aspect ratio target: ~2:1 so the figure spans the full text width
    # of a LaTeX paper at roughly the top 30% of the page. Width is
    # generous enough that label_pad_left/right plus the column gaps
    # leave the flow itself uncompressed; footer_pad shrinks now that
    # the graph-properties strip is compact and connector-free.
    width, height = 1400.0, 820.0
    footer_pad = 8.0
    nodes, links = build_graph()
    layout(nodes, links, width=width, height=height, footer_pad=footer_pad)
    svg = render_svg(nodes, links, width=width, height=height,
                     footer_pad=footer_pad)

    out_dir = Path(__file__).resolve().parent / "figs"
    out_dir.mkdir(parents=True, exist_ok=True)
    svg_path = out_dir / "sankey_pipeline.svg"
    svg_path.write_text(svg, encoding="utf-8")
    print(f"wrote {svg_path}")

    # SVG -> PDF via svglib + reportlab (pure Python). PNG export needs
    # cairo (renderPM) which isn't on the typical Windows install — open
    # the SVG in a browser and screenshot if a raster preview is needed.
    try:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPDF
        drawing = svg2rlg(str(svg_path))
        pdf_path = out_dir / "sankey_pipeline.pdf"
        renderPDF.drawToFile(drawing, str(pdf_path))
        print(f"wrote {pdf_path}")
    except Exception as e:
        print(f"  PDF conversion failed: {type(e).__name__}: {e}")
        print(f"  open {svg_path} or convert manually "
              f"(e.g. `inkscape sankey_pipeline.svg --export-type=pdf`)")


if __name__ == "__main__":
    main()
