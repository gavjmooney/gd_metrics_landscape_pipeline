"""Publication figures — Does graph structure affect drawing quality?

Companion notebook to ``paper/main.tex`` (GD'26, Track 2 long paper).
Four figures backed by an interactive cluster-threshold control
block at the top:

- Fig 1 (RQ1): Per-metric variance share — graph identity vs layout
  vs residual.
- Fig 2 (RQ2 setup): Spearman correlations between structural
  properties and layout-averaged readability metrics.
- Fig 3 (RQ2a): Property-cluster (and optional `layout`) variance
  partition — each feature group's Shapley R² contribution per metric,
  with Σ-clusters / Residual summary columns.
- Fig 4 (RQ2c): Cluster-representative per-bin readability matrix —
  for each (metric × property representative), min/max ribbon + ceiling
  line + median dot across n equal-count or equal-width bins of the
  property.
  Pre-computed bundles for n ∈ {3..10} keep the slider responsive.

The slider block at the top controls hierarchical clustering of
**properties**, **metrics**, and **layouts** by their pairwise
Spearman |ρ| — all three sliders run from 0 to 1, and their
dendrograms are shown alongside so the reader can pick a sensible
threshold. The property clustering drives the column layout of
Figs 2, 3, and 4; the metric clustering drives the row ordering; the
layout clustering is exploratory (a check on the theory-based layout
families). The two composite metrics (`quality`, `empirical_quality`)
are excluded from metric clustering — they remain singletons and are
positioned together at the end of the metric axis.

The exploratory companion (``exploratory_visualisations.py``) has the
small-multiples violins, scatter views, sensitivity checks, and
alternative model variants (Ridge, OLS-on-all).

Run with::

    marimo edit analysis/paper_visualisations.py
"""

import marimo

__generated_with = "0.23.4"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import marimo as mo

    return (mo,)


@app.cell
def _():
    from pathlib import Path as _Path

    # ─────────────────────────────────────────────────────────────────
    # Set this to the root of the pipeline output you want to analyse.
    # The directory must contain:
    #   <PIPELINE_DIR>/manifest.csv      (one row per graph_id)
    #   <PIPELINE_DIR>/metrics/          (one CSV per layout algorithm)
    # Layouts are discovered from the CSV filenames in metrics/.
    # The parquet cache lives at <PIPELINE_DIR>/.analysis_cache/.
    # ─────────────────────────────────────────────────────────────────
    PIPELINE_DIR = _Path(__file__).resolve().parent / "data"

    # Force a fresh read from the underlying CSVs (bypassing the parquet
    # cache) — set True after the pipeline has produced new metric values.
    REFRESH = False

    # ─────────────────────────────────────────────────────────────────
    # Directory where each chart cell writes a PDF copy of the figure
    # as a side effect. The notebook still renders everything inline
    # regardless — set ``EXPORT_DIR = None`` to disable PDF export.
    # ─────────────────────────────────────────────────────────────────
    EXPORT_DIR = _Path(__file__).resolve().parent / "figs"
    return EXPORT_DIR, PIPELINE_DIR, REFRESH


@app.cell(hide_code=True)
def _():
    import altair as alt
    import numpy as np
    import pandas as pd

    from data_prep import (
        METRICS,
        STRUCTURAL_PROPERTIES,
        discover_layouts,
        load_drawings_from,
    )

    # vegafusion is intentionally NOT used: it breaks per-row faceting
    # of layered mark_text in Fig 4 (text mis-routes into non-EQ rows).
    # All charts here use pre-aggregated frames so disable_max_rows() is
    # sufficient to avoid the 5K-row safety check.
    alt.data_transformers.disable_max_rows()
    return METRICS, STRUCTURAL_PROPERTIES, alt, load_drawings_from, np, pd


@app.cell(hide_code=True)
def _(EXPORT_DIR):
    # PDF-export side-effect helper used by every chart cell below.
    # Accepts either an Altair chart (uses ``.save`` via vl-convert) or
    # a matplotlib Figure (uses ``.savefig``). Failures are warned, not
    # raised, so a broken PDF export never breaks the interactive
    # notebook view — the inline figure still renders.
    def save_chart_pdf(chart, name):
        if EXPORT_DIR is None:
            return
        try:
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            _path = EXPORT_DIR / f"{name}.pdf"
            if hasattr(chart, "savefig"):
                chart.savefig(str(_path), format="pdf", bbox_inches="tight")
            else:
                chart.save(str(_path), format="pdf")
        except Exception as _exc:
            import warnings as _warnings
            _warnings.warn(
                f"PDF export failed for {name}: {_exc}", stacklevel=2,
            )

    return (save_chart_pdf,)


@app.cell(hide_code=True)
def _():
    # Display labels: snake_case → natural language. Used in axis
    # titles, tooltips, legends, and chart titles. Keep the snake_case
    # as the data-frame column key but show the friendly string to
    # the reader.
    METRIC_LABEL = {
        "angular_resolution": "Angular resolution",
        "aspect_ratio": "Aspect ratio",
        "crossing_angle": "Crossing angle",
        "edge_crossings": "Edge crossings",
        "edge_length_deviation": "Edge length deviation",
        "edge_orthogonality": "Edge orthogonality",
        "kruskal_stress": "Kruskal stress metric",
        "neighbourhood_preservation": "Neighbourhood preservation",
        "node_edge_occlusion": "Node–edge occlusion",
        "node_resolution": "Node resolution",
        "node_uniformity": "Node uniformity",
        "quality": "Overall Quality (mean of all metrics)",
        "empirical_quality": "Empirical quality (3-metric)",
    }

    PROPERTY_LABEL = {
        "n_nodes": "Node count",
        "n_edges": "Edge count",
        "density": "Density",
        "min_degree": "Min degree",
        "max_degree": "Max degree",
        "mean_degree": "Mean degree",
        "degree_std": "Degree std. dev.",
        "diameter": "Diameter",
        "radius": "Radius",
        "avg_shortest_path_length": "Mean shortest path",
        "n_triangles": "Triangle count",
        "average_clustering": "Mean local clustering",
        "transitivity": "Transitivity",
        "degree_assortativity": "Degree assortativity",
        "n_biconnected_components": "Biconn. components",
        "degeneracy": "Degeneracy",
        "crossing_number_lb_euler": "Crossing-number lower bound",
    }

    # Compact variants for the dense matrix in Figure 5: line-wrapped so
    # facet headers don't hog a full LIPIcs column of horizontal space.
    # Vega-Lite renders `\n` as a hard line break in label text. Used
    # only by the cluster-rep ribbon matrix and the per-metric ceiling
    # trajectories — the bar / heatmap charts elsewhere in the notebook
    # keep the single-line labels because they have width to spare.
    METRIC_LABEL_COMPACT = {
        **METRIC_LABEL,
        "edge_length_deviation": "Edge length\ndeviation",
        "edge_orthogonality": "Edge\northogonality",
        "neighbourhood_preservation": "Nbhd.\npreservation",
        "node_edge_occlusion": "Node–edge\nocclusion",
        "kruskal_stress": "Kruskal\nstress",
        "node_resolution": "Node\nresolution",
        "node_uniformity": "Node\nuniformity",
        "angular_resolution": "Angular\nresolution",
        "aspect_ratio": "Aspect\nratio",
        "crossing_angle": "Crossing\nangle",
        "edge_crossings": "Edge\ncrossings",
        "quality": "Quality\n(11-mean)",
        "empirical_quality": "Emp. quality\n(3-mean)",
    }

    PROPERTY_LABEL_COMPACT = {
        **PROPERTY_LABEL,
        "n_nodes": "Node\ncount",
        "n_edges": "Edge\ncount",
        "min_degree": "Min\ndegree",
        "max_degree": "Max\ndegree",
        "mean_degree": "Mean\ndegree",
        "degree_std": "Degree\nstd. dev.",
        "avg_shortest_path_length": "Mean\nshortest\npath",
        "n_triangles": "Triangle\ncount",
        "average_clustering": "Mean\nlocal\nclustering",
        "degree_assortativity": "Degree\nassortativity",
        "n_biconnected_components": "Biconn.\ncomponents",
        "crossing_number_lb_euler": "Crossing-num.\nlower\nbound",
    }

    # 2–3 character acronyms — historical labels for the ribbon matrix
    # rows; retained for callers that still want a compact label.
    # Convention follows Mooney et al.'s TVCG landscape paper (AR, Asp,
    # CA, EC, EO, KSM, NP, NR, NU) plus the new metric NEO (node–edge
    # occlusion) and Q / EQ for the two composites.
    METRIC_LABEL_ACRONYM = {
        "angular_resolution": "AR",
        "aspect_ratio": "Asp",
        "crossing_angle": "CA",
        "edge_crossings": "EC",
        "edge_length_deviation": "ELD",
        "edge_orthogonality": "EO",
        "kruskal_stress": "KSM",
        "neighbourhood_preservation": "NP",
        "node_edge_occlusion": "NEO",
        "node_resolution": "NR",
        "node_uniformity": "NU",
        "quality": "Q",
        "empirical_quality": "EQ",
    }

    # Full-name metric labels with manual line breaks tuned so each
    # line fits within the ribbon-matrix row's vertical extent when
    # rotated -90°. Used by Fig 4 as the row header labels.
    METRIC_LABEL_WRAPPED = {
        "angular_resolution": "Angular\nresolution",
        "aspect_ratio": "Aspect\nratio",
        "crossing_angle": "Crossing\nangle",
        "edge_crossings": "Edge\ncrossings",
        "edge_length_deviation": "Edge length\ndeviation",
        "edge_orthogonality": "Edge\northogonality",
        "kruskal_stress": "Kruskal\nstress\nmetric",
        "neighbourhood_preservation": "Neighbourhood\npreservation",
        "node_edge_occlusion": "Node–edge\nocclusion",
        "node_resolution": "Node\nresolution",
        "node_uniformity": "Node\nuniformity",
        "quality": "Overall Quality\n(mean of all\nmetrics)",
        "empirical_quality": "Empirical\nquality\n(3-metric)",
    }
    return (
        METRIC_LABEL,
        METRIC_LABEL_ACRONYM,
        METRIC_LABEL_WRAPPED,
        PROPERTY_LABEL,
        PROPERTY_LABEL_COMPACT,
    )


@app.cell(hide_code=True)
def _(STRUCTURAL_PROPERTIES):
    # Properties dropped from downstream analysis:
    # - `crossing_number_lb_bipartite` — ~80% NaN (defined only on
    #   bipartite graphs).
    # - All `is_*` binary indicators — standardised β on a 0/1 column
    #   is awkward to interpret (β represents change per ~0.5 SD), the
    #   smaller classes (`is_eulerian`, `is_regular`) produce noisy
    #   point estimates, and the bivariate / OLS analyses become much
    #   easier to read on a continuous-only feature set. Cohort-level
    #   effects of structural class are better-shown as group
    #   comparisons (left to a follow-up notebook).
    # `degree_assortativity` is kept despite being undefined on the
    # 3.3% of graphs that are regular — the Spearman heatmaps use
    # pairwise complete cases and the HGBR variance partition handles
    # NaN natively, so excluding it was costing a usable property
    # for no real gain.
    EXCLUDED_PROPERTIES = tuple(
        p for p in STRUCTURAL_PROPERTIES
        if p == "crossing_number_lb_bipartite"
        or p.startswith("is_")
    )
    PROPERTIES = [p for p in STRUCTURAL_PROPERTIES if p not in EXCLUDED_PROPERTIES]
    return (PROPERTIES,)


@app.cell(hide_code=True)
def _(METRICS):
    # Two composite metrics added on top of the 11 base metrics.
    #
    # `quality` — uniform-weight mean of all 11 base metrics. A
    # naive composite that weighs every aesthetic equally; useful as
    # a single "overall drawing quality" target.
    #
    # `empirical_quality` — mean of the three base metrics shown by
    # recent human-subject work (Mooney et al., 2026, in submission)
    # to most strongly predict task accuracy on shortest-path
    # identification: node-edge occlusion, edge crossings, and
    # angular resolution. This is an empirically-weighted alternative
    # to the uniform `quality` composite.
    EMPIRICAL_QUALITY_METRICS = (
        "node_edge_occlusion",
        "edge_crossings",
        "angular_resolution",
    )
    DERIVED_METRICS = ("quality", "empirical_quality")
    METRICS_PLUS = list(METRICS) + list(DERIVED_METRICS)
    return EMPIRICAL_QUALITY_METRICS, METRICS_PLUS


@app.cell(hide_code=True)
def _(
    EMPIRICAL_QUALITY_METRICS,
    METRICS,
    PIPELINE_DIR,
    REFRESH,
    load_drawings_from,
):
    # Per-drawing frame (one row per (graph_id, layout)) merged with
    # the graph-level structural properties. Layouts are discovered
    # from `<PIPELINE_DIR>/metrics/*.csv`. Two composite metrics are
    # added: `quality` (mean of all 11 base metrics) and
    # `empirical_quality` (mean of the three task-accuracy predictors).
    _raw = load_drawings_from(PIPELINE_DIR, refresh=REFRESH)
    drawings = _raw.assign(
        quality=_raw[list(METRICS)].mean(axis=1, skipna=True),
        empirical_quality=_raw[list(EMPIRICAL_QUALITY_METRICS)].mean(
            axis=1, skipna=True
        ),
    )
    return (drawings,)


@app.cell(hide_code=True)
def _(METRICS_PLUS, drawings):
    # Per-graph envelope table: one row per graph_id with min / max /
    # mean / range across that graph's layouts for each metric (base
    # metrics + the two composites), plus the structural properties.
    _agg = drawings.groupby("graph_id")[list(METRICS_PLUS)].agg(
        ["min", "max", "mean"]
    )
    _agg.columns = [f"{m}_{stat}" for m, stat in _agg.columns]
    for _m in METRICS_PLUS:
        _agg[f"{_m}_range"] = _agg[f"{_m}_max"] - _agg[f"{_m}_min"]
    _agg["n_drawings"] = drawings.groupby("graph_id").size()
    _agg = _agg.reset_index()
    # First-row-per-graph pulls the structural properties (constant
    # within a graph) without re-loading the manifest.
    _props = (
        drawings.drop_duplicates("graph_id")
        .set_index("graph_id")
        .drop(columns=list(METRICS_PLUS), errors="ignore")
    )
    envelope_table = _agg.merge(
        _props, on="graph_id", how="left", suffixes=("", "_dup")
    )
    envelope_table = envelope_table[
        [c for c in envelope_table.columns if not c.endswith("_dup")]
    ]
    return (envelope_table,)


@app.cell(hide_code=True)
def _(mo):
    prop_cluster_slider = mo.ui.slider(
        # Range matches the trimmed `_thresholds` sweep in the
        # variance-partition bundle so every slider value resolves to
        # a precomputed row.
        start=0.65, stop=0.85, step=0.05, value=0.75,
        label="Property cluster threshold |ρ|", show_value=True,
    )
    metric_cluster_slider = mo.ui.slider(
        start=0.0, stop=1.0, step=0.05, value=0.85,
        label="Metric cluster threshold |ρ|", show_value=True,
    )
    layout_cluster_slider = mo.ui.slider(
        start=0.0, stop=1.0, step=0.05, value=0.7,
        label="Layout cluster threshold |ρ|", show_value=True,
    )
    return layout_cluster_slider, metric_cluster_slider, prop_cluster_slider


@app.cell(hide_code=True)
def _(PROPERTIES, envelope_table, np):
    # Compute the property linkage once (independent of slider). Slider
    # only drives the `fcluster` cut in the downstream cell, so dragging
    # the slider is cheap.
    from scipy.cluster.hierarchy import (
        fcluster as _fcluster,
        leaves_list as _leaves_list,
        linkage as _linkage,
    )
    from scipy.spatial.distance import squareform as _squareform

    _prop_frame = envelope_table[PROPERTIES].apply(
        lambda c: c.astype(float) if c.dtype == bool else c
    )
    _prop_corr = _prop_frame.corr(method="spearman")
    _abs = np.nan_to_num(_prop_corr.abs().to_numpy(), nan=0.0)
    _abs = (_abs + _abs.T) / 2
    np.fill_diagonal(_abs, 1.0)
    _dist = np.clip(1.0 - _abs, 0.0, 2.0)
    np.fill_diagonal(_dist, 0.0)
    prop_linkage_Z = _linkage(_squareform(_dist, checks=False), method="average")
    _leaf_idx = _leaves_list(prop_linkage_Z)
    prop_leaf_order_static = [PROPERTIES[i] for i in _leaf_idx]
    # Re-export scipy helpers so downstream bundles can share them.
    fcluster = _fcluster
    linkage = _linkage
    squareform = _squareform
    return (
        fcluster,
        linkage,
        prop_leaf_order_static,
        prop_linkage_Z,
        squareform,
    )


@app.cell(hide_code=True)
def _(
    PROPERTIES,
    PROPERTY_LABEL,
    fcluster,
    prop_cluster_slider,
    prop_leaf_order_static,
    prop_linkage_Z,
):
    # Cut the dendrogram at the slider's threshold and build the
    # cluster / representative / membership tables that downstream
    # figures consume. Property leaf order does NOT depend on the
    # threshold — it's the dendrogram's fixed leaf order.
    REPRESENTATIVE_PREFERENCES = {
        "n_edges": 2, "n_nodes": 1,
        "avg_shortest_path_length": 2, "diameter": 1, "radius": 0,
        "transitivity": 2, "average_clustering": 1, "n_triangles": 0,
        "mean_degree": 2, "degeneracy": 1,
        "max_degree": 2, "degree_std": 1,
    }

    _threshold = float(prop_cluster_slider.value)
    # `fcluster` cuts at distance ≤ t; distance = 1 − |ρ|, so the
    # cut threshold is 1 − |ρ_min|. A tiny epsilon keeps the
    # rightmost endpoint (|ρ|=1.0 → cut at 0.0) producing singletons.
    _cut = max(1e-9, 1.0 - _threshold)
    _ids = fcluster(prop_linkage_Z, t=_cut, criterion="distance")
    prop_clusters = dict(zip(PROPERTIES, _ids.tolist()))

    _by_cluster = {}
    for _label, _cid in prop_clusters.items():
        _by_cluster.setdefault(_cid, []).append(_label)
    _cluster_to_rep = {}
    for _cid, _members in _by_cluster.items():
        _ranked = sorted(
            _members,
            key=lambda m: (-REPRESENTATIVE_PREFERENCES.get(m, 0), m),
        )
        _cluster_to_rep[_cid] = _ranked[0]

    prop_leaf_order = list(prop_leaf_order_static)
    cluster_reps = [
        p for p in prop_leaf_order if p in set(_cluster_to_rep.values())
    ]
    cluster_name = {
        _cid: PROPERTY_LABEL.get(_rep, _rep)
        for _cid, _rep in _cluster_to_rep.items()
    }
    # Editorial overrides — when a cluster's exact member set matches
    # one of the documented seven clusters at the default 0.75
    # threshold, replace the auto-generated rep-label with a concept
    # name that describes the cluster rather than its lead member.
    # Slider positions that produce a non-canonical membership fall
    # through to the auto label.
    _CLUSTER_NAME_OVERRIDES = {
        frozenset({"n_nodes", "n_edges"}): "Size (|V|, |E|)",
        frozenset({"max_degree", "degree_std"}): "Degree heterogeneity",
        frozenset({
            "n_triangles", "average_clustering", "transitivity",
            "mean_degree", "degeneracy",
        }): "Local density / clustering",
        frozenset({
            "density", "radius", "diameter", "avg_shortest_path_length",
        }): "Density / distance",
        frozenset({"min_degree", "n_biconnected_components"}):
            "Local connectivity",
    }
    for _cid, _members in _by_cluster.items():
        _override = _CLUSTER_NAME_OVERRIDES.get(frozenset(_members))
        if _override is not None:
            cluster_name[_cid] = _override
    cluster_members = {
        _cid: [
            PROPERTY_LABEL.get(m, m)
            for m in prop_leaf_order
            if m in set(_by_cluster[_cid])
        ]
        for _cid in _by_cluster
    }
    return cluster_name, prop_clusters, prop_leaf_order


@app.cell(hide_code=True)
def _(
    PROPERTIES,
    PROPERTY_LABEL,
    mo,
    prop_cluster_slider,
    prop_linkage_Z,
    save_chart_pdf,
):
    # Slider directly above its dendrogram (paired layout). Slider-
    # driven red dashed line shows the active cut height; leaf order
    # is fixed by the linkage and matches the axis order used by
    # Figs 2 and 3.
    import matplotlib.pyplot as _plt
    from scipy.cluster.hierarchy import dendrogram as _dendrogram

    _labels = [PROPERTY_LABEL.get(p, p) for p in PROPERTIES]
    _threshold = float(prop_cluster_slider.value)
    _cut = max(1e-9, 1.0 - _threshold)

    _fig, _ax = _plt.subplots(figsize=(11, 3.6))
    _dendrogram(
        prop_linkage_Z,
        labels=_labels, ax=_ax,
        color_threshold=_cut,
        leaf_rotation=60, leaf_font_size=9,
    )
    _ax.axhline(
        _cut, color="#C44E52", linestyle="--", linewidth=1.2,
        label=f"|ρ| ≥ {_threshold:.2f}  (distance ≤ {_cut:.2f})",
    )
    _ax.set_ylabel("Distance  (1 − |ρ|)")
    _ax.set_title("Property correlation dendrogram — Spearman ρ, average linkage")
    _ax.legend(loc="upper right", fontsize=8)
    _ax.set_ylim(0, 1.05)
    _fig.tight_layout()
    save_chart_pdf(_fig, "dendrogram_property")
    mo.vstack([prop_cluster_slider, _fig])
    return


@app.cell(hide_code=True)
def _(METRICS, drawings, linkage, np, squareform):
    from scipy.cluster.hierarchy import leaves_list as _leaves_list

    _metric_frame = drawings[list(METRICS)]
    _metric_corr = _metric_frame.corr(method="spearman")
    _abs = np.nan_to_num(_metric_corr.abs().to_numpy(), nan=0.0)
    _abs = (_abs + _abs.T) / 2
    np.fill_diagonal(_abs, 1.0)
    _dist = np.clip(1.0 - _abs, 0.0, 2.0)
    np.fill_diagonal(_dist, 0.0)
    metric_linkage_Z = linkage(
        squareform(_dist, checks=False), method="average"
    )
    _leaf_idx = _leaves_list(metric_linkage_Z)
    base_metric_leaf_order = [METRICS[i] for i in _leaf_idx]
    return base_metric_leaf_order, metric_linkage_Z


@app.cell(hide_code=True)
def _(
    METRICS,
    METRIC_LABEL,
    METRIC_LABEL_ACRONYM,
    base_metric_leaf_order,
    fcluster,
    metric_cluster_slider,
    metric_linkage_Z,
):
    _threshold = float(metric_cluster_slider.value)
    _cut = max(1e-9, 1.0 - _threshold)
    _ids = fcluster(metric_linkage_Z, t=_cut, criterion="distance")
    base_metric_clusters = dict(zip(METRICS, _ids.tolist()))

    # Composites stay singletons regardless of threshold; positioned
    # together at the end of the metric leaf order.
    COMPOSITE_METRICS = ("quality", "empirical_quality")
    metric_leaf_order = list(base_metric_leaf_order) + list(COMPOSITE_METRICS)

    _next_id = (max(_ids.tolist()) if len(_ids) else 0) + 1
    metric_clusters = dict(base_metric_clusters)
    for _i, _m in enumerate(COMPOSITE_METRICS):
        metric_clusters[_m] = _next_id + _i

    # Pick a representative per metric cluster — the metric that
    # appears earliest in the dendrogram leaf order of the cluster.
    # Composites are always their own cluster (singletons), so they
    # always become their own rep at the end of the rep list.
    _rep_seen = set()
    metric_cluster_reps = []
    for _m in metric_leaf_order:
        _cid = metric_clusters[_m]
        if _cid in _rep_seen:
            continue
        _rep_seen.add(_cid)
        metric_cluster_reps.append(_m)

    # Cluster size lookup, and a display-label map that suffixes
    # "(n=N)" on multi-member clusters — symmetric with the property
    # cluster convention. Two flavours: full names (METRIC_LABEL) for
    # Fig 3, acronym (METRIC_LABEL_ACRONYM) for Fig 4's compact axis.
    _cluster_size_by_cid = {}
    for _m, _cid in metric_clusters.items():
        _cluster_size_by_cid[_cid] = _cluster_size_by_cid.get(_cid, 0) + 1

    def _display(_m, _label_map):
        _base = _label_map.get(_m, _m)
        _n = _cluster_size_by_cid[metric_clusters[_m]]
        return _base if _n == 1 else f"{_base} (n={_n})"

    metric_rep_display = {
        _m: _display(_m, METRIC_LABEL) for _m in metric_cluster_reps
    }
    metric_rep_display_acronym = {
        _m: _display(_m, METRIC_LABEL_ACRONYM) for _m in metric_cluster_reps
    }
    return (metric_leaf_order,)


@app.cell(hide_code=True)
def _(
    METRICS,
    METRIC_LABEL,
    metric_cluster_slider,
    metric_linkage_Z,
    mo,
    save_chart_pdf,
):
    # Slider directly above its dendrogram (paired layout). The 11 base
    # metrics are clustered; `quality` and `empirical_quality` are
    # appended as detached singleton stubs to the right of a visible
    # gap so the reader sees they are excluded from the clustering by
    # design.
    import matplotlib.pyplot as _plt
    from scipy.cluster.hierarchy import dendrogram as _dendrogram

    _labels = [METRIC_LABEL.get(m, m) for m in METRICS]
    _threshold = float(metric_cluster_slider.value)
    _cut = max(1e-9, 1.0 - _threshold)

    _fig, _ax = _plt.subplots(figsize=(11, 3.6))
    _dendrogram(
        metric_linkage_Z,
        labels=_labels, ax=_ax,
        color_threshold=_cut,
        leaf_rotation=60, leaf_font_size=9,
    )
    _ax.axhline(
        _cut, color="#C44E52", linestyle="--", linewidth=1.2,
        label=f"|ρ| ≥ {_threshold:.2f}  (distance ≤ {_cut:.2f})",
    )
    _ax.set_ylabel("Distance  (1 − |ρ|)")
    _ax.set_title(
        "Metric correlation dendrogram — Spearman ρ, average linkage  "
        "(composite singletons on the right)"
    )
    _ax.legend(loc="upper right", fontsize=8)
    _ax.set_ylim(0, 1.10)

    # Append composite singletons after the dendrogram with a gap.
    _xs = sorted(set(_ax.get_xticks()))
    if len(_xs) >= 2:
        _x_step = (_xs[-1] - _xs[0]) / (len(_xs) - 1)
    else:
        _x_step = 10.0
    _gap_x = _xs[-1] + 1.8 * _x_step
    for _i, _m in enumerate(["quality", "empirical_quality"]):
        _x = _gap_x + _i * _x_step
        _ax.plot([_x, _x], [0, 0.025], color="#444", linewidth=1.3)
        _ax.text(
            _x, -0.015, METRIC_LABEL.get(_m, _m),
            ha="right", va="top", rotation=60, fontsize=9, color="#444",
        )
    _ax.set_xlim(_xs[0] - _x_step, _gap_x + 2.5 * _x_step)
    _fig.tight_layout()
    save_chart_pdf(_fig, "dendrogram_metric")
    mo.vstack([metric_cluster_slider, _fig])
    return


@app.cell(hide_code=True)
def _(drawings, linkage, np, squareform):
    from scipy.cluster.hierarchy import leaves_list as _leaves_list

    _pivot = drawings.pivot_table(
        index="graph_id", columns="layout",
        values="quality", aggfunc="first",
    )
    layout_names = list(_pivot.columns)
    _layout_corr = _pivot.corr(method="spearman")
    _abs = np.nan_to_num(_layout_corr.abs().to_numpy(), nan=0.0)
    _abs = (_abs + _abs.T) / 2
    np.fill_diagonal(_abs, 1.0)
    _dist = np.clip(1.0 - _abs, 0.0, 2.0)
    np.fill_diagonal(_dist, 0.0)
    layout_linkage_Z = linkage(
        squareform(_dist, checks=False), method="average"
    )
    _leaf_idx = _leaves_list(layout_linkage_Z)
    layout_leaf_order_static = [layout_names[i] for i in _leaf_idx]
    layout_corr = _layout_corr
    return layout_leaf_order_static, layout_linkage_Z, layout_names


@app.cell(hide_code=True)
def _(
    fcluster,
    layout_cluster_slider,
    layout_leaf_order_static,
    layout_linkage_Z,
    layout_names,
):
    _threshold = float(layout_cluster_slider.value)
    _cut = max(1e-9, 1.0 - _threshold)
    _ids = fcluster(layout_linkage_Z, t=_cut, criterion="distance")
    layout_clusters = dict(zip(layout_names, _ids.tolist()))

    layout_leaf_order = list(layout_leaf_order_static)
    _members_by_cid = {}
    for _label in layout_leaf_order:
        _members_by_cid.setdefault(
            layout_clusters[_label], []
        ).append(_label)
    layout_cluster_members = {
        _cid: list(_ms) for _cid, _ms in _members_by_cid.items()
    }
    return (layout_clusters,)


@app.cell(hide_code=True)
def _(
    layout_cluster_slider,
    layout_linkage_Z,
    layout_names,
    mo,
    save_chart_pdf,
):
    # Slider directly above its dendrogram (paired layout).
    import matplotlib.pyplot as _plt
    from scipy.cluster.hierarchy import dendrogram as _dendrogram

    _threshold = float(layout_cluster_slider.value)
    _cut = max(1e-9, 1.0 - _threshold)

    _fig, _ax = _plt.subplots(figsize=(11, 3.6))
    _dendrogram(
        layout_linkage_Z,
        labels=layout_names, ax=_ax,
        color_threshold=_cut,
        leaf_rotation=45, leaf_font_size=9,
    )
    _ax.axhline(
        _cut, color="#C44E52", linestyle="--", linewidth=1.2,
        label=f"|ρ| ≥ {_threshold:.2f}  (distance ≤ {_cut:.2f})",
    )
    _ax.set_ylabel("Distance  (1 − |ρ|)")
    _ax.set_title(
        "Layout correlation dendrogram — Spearman ρ over the "
        "per-graph `quality` vector"
    )
    _ax.legend(loc="upper right", fontsize=8)
    _ax.set_ylim(0, 1.05)
    _fig.tight_layout()
    save_chart_pdf(_fig, "dendrogram_layout")
    mo.vstack([layout_cluster_slider, _fig])
    return


@app.cell(hide_code=True)
def _():
    # Theory-based layout families (mirror of data_prep.LAYOUT_FAMILY).
    # Re-declared here as a notebook-local map so the layout-clusters
    # cell can annotate empirical clusters with the theory label
    # without re-importing.
    LAYOUT_FAMILY_MAP = {
        "random": "Baseline",
        "circular": "Baseline",
        "spectral": "Spectral",
        "planar": "Embedding",
        "radial-tree": "Embedding",
        "fruchterman-reingold": "Force-directed",
        "kamada-kawai": "Force-directed",
        "FMMM": "Multilevel force",
        "stress-majorization": "Stress / MDS",
        "pivot-MDS": "Stress / MDS",
        "sugiyama": "Layered",
        "dot-ortho": "Orthogonal",
        "planarization-ortho": "Orthogonal",
        "HOLA": "Constraint hybrid",
        "arc-bfs": "Curved (custom)",
        "curated": "Curator",
    }
    return


@app.cell(hide_code=True)
def _(METRICS_PLUS, drawings, pd):
    def sequential_variance(df, metric, factors):
        """Type-I variance decomposition by sequential residualisation.

        For each factor in ``factors``, subtract the per-group mean of
        the *current* residual and record the SS reduction.
        Components sum to 1.0 by construction. Returns ``None`` if the
        metric is empty or constant on the dropna-ed slice."""
        sub = df[[metric, *factors]].dropna()
        if len(sub) == 0:
            return None
        y = sub[metric].to_numpy()
        ss_total = float(((y - y.mean()) ** 2).sum())
        if ss_total == 0:
            return None
        residual = y - y.mean()
        ss_prev = ss_total
        out = {}
        for col in factors:
            col_means = (
                sub.assign(_r=residual)
                .groupby(col)["_r"]
                .transform("mean")
                .to_numpy()
            )
            residual = residual - col_means
            ss_new = float((residual ** 2).sum())
            out[f"eta2_{col}"] = (ss_prev - ss_new) / ss_total
            ss_prev = ss_new
        out["eta2_residual"] = ss_prev / ss_total
        return out

    _rows = []
    for _m in METRICS_PLUS:
        _r = sequential_variance(drawings, _m, ["graph_id", "layout"])
        if _r is None:
            continue
        _rows.append(
            {
                "metric": _m,
                "Graph": _r["eta2_graph_id"],
                "Layout (given graph)": _r["eta2_layout"],
                "Residual": _r["eta2_residual"],
            }
        )
    variance_components = pd.DataFrame(_rows)
    return (variance_components,)


@app.cell(hide_code=True)
def _(METRICS, METRIC_LABEL, alt, pd, save_chart_pdf, variance_components):
    _components = ["Graph", "Layout (given graph)", "Residual"]
    _long = variance_components.melt(
        id_vars="metric", value_vars=_components,
        var_name="Variance source", value_name="share",
    )
    _long["metric_label"] = _long["metric"].map(METRIC_LABEL)

    # Sort: base metrics first (by graph share descending), then
    # composites pinned to the bottom. The thick horizontal rule
    # below sits at the boundary between the two groups.
    _df_sorted = variance_components.copy()
    _df_sorted["is_composite"] = ~_df_sorted["metric"].isin(set(METRICS))
    _df_sorted = _df_sorted.sort_values(
        ["is_composite", "Graph"], ascending=[True, False],
    )
    _metric_order = _df_sorted["metric"].map(METRIC_LABEL).tolist()
    _composites_present = _df_sorted.loc[
        _df_sorted["is_composite"], "metric"
    ].map(METRIC_LABEL).tolist()
    _first_composite_label = (
        _composites_present[0] if _composites_present else None
    )

    _bars = (
        alt.Chart(_long)
        .mark_bar()
        .encode(
            y=alt.Y(
                "metric_label:N", sort=_metric_order,
                title="Readability metric",
            ),
            x=alt.X(
                "share:Q",
                stack="normalize",
                axis=alt.Axis(format="%"),
                title="Share of total variance (η², Type-I sequential)",
            ),
            color=alt.Color(
                "Variance source:N",
                scale=alt.Scale(
                    domain=_components,
                    range=["#3B6FB6", "#E08436", "#B8BDC4"],
                ),
                sort=_components,
                legend=alt.Legend(orient="bottom", title=None),
            ),
            order=alt.Order("Variance source:N", sort="ascending"),
            tooltip=[
                alt.Tooltip("metric_label:N", title="Metric"),
                alt.Tooltip("Variance source:N"),
                alt.Tooltip("share:Q", format=".1%", title="Share"),
            ],
        )
    )
    if _first_composite_label is not None:
        # Thick horizontal rule at the TOP of the first composite =
        # boundary between base and composite metrics.
        _hrule = alt.Chart(
            pd.DataFrame({"metric_label": [_first_composite_label]})
        ).mark_rule(stroke="#222", strokeWidth=3).encode(
            y=alt.Y(
                "metric_label:N", sort=_metric_order,
                bandPosition=0,
            ),
        )
        fig1_chart = _bars + _hrule
    else:
        fig1_chart = _bars

    fig1_chart = fig1_chart.properties(
        width=520, height=320,
        title=alt.TitleParams(
            text="Variance share of each readability metric: graph vs. layout vs. residual",
            anchor="middle",
        ),
    )
    save_chart_pdf(fig1_chart, "fig1_variance_components")
    fig1_chart
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Each bar shows how a metric’s variance is split across three sources: the graph itself, the layout chosen for that graph, and the remaining residual. Graph-dominated metrics are mostly determined by the input graph, before any layout is selected. Layout-dominated metrics vary mainly with the drawing choice, while residual-heavy metrics are not well explained by either factor. The thick horizontal line separates the eleven base metrics from the two composite scores.
    """)
    return


@app.cell(hide_code=True)
def _(METRICS_PLUS, PROPERTIES, envelope_table, np, pd):
    # Spearman ρ between each property and each metric's envelope-mean,
    # computed on the per-graph table (one row per graph). Booleans
    # are already excluded from PROPERTIES; remaining NaNs come from a
    # handful of graphs missing a distance metric. Includes the two
    # composite metrics (`quality`, `empirical_quality`) alongside the
    # 11 base metrics.
    _rows = []
    for _prop in PROPERTIES:
        _x = envelope_table[_prop].astype(float)
        for _metric in METRICS_PLUS:
            _y = envelope_table[f"{_metric}_mean"]
            _mask = _x.notna() & _y.notna()
            if _mask.sum() < 30:
                continue
            _rho = float(_x[_mask].corr(_y[_mask], method="spearman"))
            if np.isnan(_rho):
                continue
            _rows.append({"property": _prop, "metric": _metric, "rho": _rho})
    bivariate_corr_df = pd.DataFrame(_rows)
    return (bivariate_corr_df,)


@app.cell(hide_code=True)
def _(
    METRICS,
    METRIC_LABEL,
    PROPERTY_LABEL,
    alt,
    bivariate_corr_df,
    metric_leaf_order,
    pd,
    prop_cluster_slider,
    prop_clusters,
    prop_leaf_order,
    prop_linkage_Z,
    save_chart_pdf,
):
    # Duplicate of the bivariate correlation heatmap above, with a
    # minimal dendrogram added on top — colour-coded by the property
    # cluster threshold and showing the cutoff line. Rebuilt under a
    # separate module-scope name (`fig2_chart_copy`) so marimo's "one
    # cell defines each name" rule is respected.
    _df = bivariate_corr_df.copy()
    _df["property_label"] = _df["property"].map(PROPERTY_LABEL).fillna(_df["property"])
    _df["metric_label"] = _df["metric"].map(METRIC_LABEL)
    _df["label_text"] = _df["rho"].map(
        lambda r: f"{r:+.2f}" if abs(r) >= 0.10 else ""
    )

    _x_order = [PROPERTY_LABEL.get(p, p) for p in prop_leaf_order
                if p in set(_df["property"])]
    _y_keys_in_order = [
        m for m in metric_leaf_order if m in set(_df["metric"])
    ]
    _y_order = [METRIC_LABEL.get(m, m) for m in _y_keys_in_order]

    _composites_in_y = [
        m for m in _y_keys_in_order if m not in set(METRICS)
    ]
    _first_composite_label = (
        METRIC_LABEL.get(_composites_in_y[0], _composites_in_y[0])
        if _composites_in_y else None
    )

    # Compute the dendrogram data here (rather than further down where
    # the dendrogram CHART is built) so the same scipy-assigned cluster
    # colours can drive both the dendrogram bars AND the property
    # labels on the heatmap's x-axis. Keeping a single source of truth
    # avoids the label vs. bar colour drift the user noticed.
    from scipy.cluster.hierarchy import dendrogram as _dendro_data
    _threshold = float(prop_cluster_slider.value)
    _cut = max(1e-9, 1.0 - _threshold)
    _dend = _dendro_data(
        prop_linkage_Z, no_plot=True,
        color_threshold=_cut, above_threshold_color="#bbbbbb",
    )
    _C_PALETTE = {f"C{_i}": _hex for _i, _hex in enumerate([
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ])}
    # ``leaves_color_list`` (scipy ≥ 1.4) is keyed by dendrogram leaf
    # order; the i-th entry is the colour scipy assigned to the leaf
    # at position i. Above-threshold (singleton) leaves get the
    # ``above_threshold_color`` we passed in ("#bbbbbb"), so they
    # already render as a neutral grey without special-casing.
    _leaves_color_list = _dend.get("leaves_color_list", [])
    _prop_to_color = {}
    for _idx, _leaf_label in enumerate(prop_leaf_order):
        _c_label = (
            _leaves_color_list[_idx]
            if _idx < len(_leaves_color_list)
            else "#bbbbbb"
        )
        _prop_to_color[_leaf_label] = _C_PALETTE.get(_c_label, _c_label)

    _present_props = [
        _p for _p in prop_leaf_order if _p in set(_df["property"])
    ]
    _axis_labels_df = pd.DataFrame({
        "property_label": [PROPERTY_LABEL.get(_p, _p) for _p in _present_props],
        "color": [_prop_to_color[_p] for _p in _present_props],
        # Dummy quantitative y at the TOP of the [0, 1] scale. Altair's
        # default y range puts higher data at lower pixel y, so y=1 →
        # pixel y=0 (top of the label strip). With baseline="top" the
        # text anchor is at the top of the strip — i.e., right below
        # the heatmap — which is where we want it.
        "_y": 1.0,
    })
    # Cluster boundary positions — for each adjacency where the
    # cluster id changes from one column to the next, mark the right
    # edge of the LEFT column. Rendered as a dashed vertical rule on
    # the heatmap.
    _boundary_props = []
    _prev_cid = None
    for _i, _p in enumerate(_present_props):
        _cid = prop_clusters[_p]
        if _prev_cid is not None and _cid != _prev_cid:
            _boundary_props.append(_present_props[_i - 1])
        _prev_cid = _cid
    _boundary_df = pd.DataFrame({
        "property_label": [
            PROPERTY_LABEL.get(_p, _p) for _p in _boundary_props
        ],
    })

    _heat = (
        alt.Chart(_df)
        .mark_rect()
        .encode(
            x=alt.X(
                "property_label:N", sort=_x_order,
                # Default x-axis labels suppressed — replaced by a
                # ``_label_strip`` chart vconcat'd below so each
                # property label can take its cluster's colour. Ticks
                # are kept and centred under each cell so the reader
                # can trace a column down to the label that sits
                # underneath. ``domain=False`` removes the axis line
                # itself; only the short tick marks remain.
                axis=alt.Axis(
                    labels=False, ticks=True, domain=False,
                    tickBand="center", tickColor="#555",
                    tickSize=4, tickWidth=0.8,
                ),
                title=None,
            ),
            y=alt.Y(
                "metric_label:N", sort=_y_order,
                title="Readability metric",
            ),
            color=alt.Color(
                "rho:Q",
                scale=alt.Scale(scheme="redblue", domain=[-1, 1],
                                reverse=False),
                legend=None,  # custom legend rendered on the right
            ),
            tooltip=[
                alt.Tooltip("property_label:N", title="Property"),
                alt.Tooltip("metric_label:N", title="Metric"),
                alt.Tooltip("rho:Q", format="+.3f", title="ρ"),
            ],
        )
    )
    _text = (
        alt.Chart(_df)
        .mark_text(fontSize=9)
        .encode(
            x=alt.X("property_label:N", sort=_x_order),
            y=alt.Y("metric_label:N", sort=_y_order),
            text="label_text:N",
            color=alt.condition(
                "abs(datum.rho) > 0.55",
                alt.value("white"),
                alt.value("#222"),
            ),
        )
    )

    _fig2_height = 380

    # Dashed vertical rules at cluster boundaries. ``bandPosition=1``
    # anchors the rule at the right edge of the band, so the rule sits
    # between adjacent clusters rather than overlapping a cell. Mirrors
    # the ``_hrule`` pattern used for the base/composite metric split.
    _cluster_boundaries = (
        alt.Chart(_boundary_df)
        .mark_rule(
            stroke="#374151", strokeDash=[5, 3], strokeWidth=1.1,
            opacity=0.85,
        )
        .encode(
            x=alt.X(
                "property_label:N", sort=_x_order, bandPosition=1,
            ),
        )
    )
    if _first_composite_label is not None:
        _hrule = alt.Chart(
            pd.DataFrame({"metric_label": [_first_composite_label]})
        ).mark_rule(stroke="#222", strokeWidth=3).encode(
            y=alt.Y(
                "metric_label:N", sort=_y_order,
                bandPosition=0,
            ),
        )
        _heatmap_inner = _heat + _cluster_boundaries + _text + _hrule
    else:
        _heatmap_inner = _heat + _cluster_boundaries + _text
    _heatmap_inner = _heatmap_inner.properties(
        width=620, height=_fig2_height,
    )

    # Label strip vconcat'd below the heatmap: one rotated property
    # label per column, coloured by its cluster's hex. Uses the same
    # ordinal x scale and sort order as the heatmap so vega-lite
    # aligns the columns. The ``_y`` field is a dummy quantitative
    # (all zeros) — vl-convert refuses an ``alt.value`` y inside a
    # vconcat whose sibling carries an ordinal y, so a real-but-flat
    # y encoding is needed instead.
    _LABEL_STRIP_HEIGHT = 80
    _label_strip = (
        alt.Chart(_axis_labels_df)
        .mark_text(
            angle=330, align="right", baseline="top", fontSize=11,
        )
        .encode(
            x=alt.X(
                "property_label:N", sort=_x_order,
                # ``axis=None`` hides the title too. Keep an axis
                # object but suppress every visible element except
                # the title, so "Graph structural property" still
                # renders below the rotated property labels.
                axis=alt.Axis(
                    labels=False, ticks=False, domain=False,
                ),
                title="Graph structural property",
            ),
            y=alt.Y(
                "_y:Q", axis=None,
                scale=alt.Scale(domain=[0, 1]),
            ),
            text="property_label:N",
            color=alt.Color("color:N", scale=None, legend=None),
        )
        .properties(width=620, height=_LABEL_STRIP_HEIGHT)
    )
    # ``resolve_scale(y='independent')`` keeps the heatmap's ordinal y
    # and the label strip's quantitative y from being merged into a
    # single scale (which would also break vl-convert compilation).
    fig2_chart_copy = (
        alt.vconcat(_heatmap_inner, _label_strip, spacing=0)
        .resolve_scale(y="independent")
    )

    # Custom diverging colour legend on the right: gradient (red → white
    # → blue), tick labels on the inside (next to the gradient), title
    # rotated 270° on the outside so it reads along the y axis.
    _REDBLUE_STOPS = [
        "#67001f", "#b2182b", "#d6604d", "#f4a582", "#fddbc7",
        "#f7f7f7",
        "#d1e5f0", "#92c5de", "#4393c3", "#2166ac", "#053061",
    ]
    _rho_min, _rho_max = -1.0, 1.0
    _grad_stops = [
        {"offset": _i / (len(_REDBLUE_STOPS) - 1), "color": _c}
        for _i, _c in enumerate(_REDBLUE_STOPS)
    ]
    _grad = alt.Chart(pd.DataFrame({
        "x_lo": [0], "x_hi": [1],
        "y_lo": [_rho_min], "y_hi": [_rho_max],
    })).mark_rect(
        color={
            "gradient": "linear",
            "x1": 0, "x2": 0,
            "y1": 1, "y2": 0,
            "stops": _grad_stops,
        },
    ).encode(
        x=alt.X("x_lo:Q", axis=None,
                scale=alt.Scale(domain=[0, 1])),
        x2=alt.X2("x_hi:Q"),
        y=alt.Y(
            "y_lo:Q", axis=None,
            scale=alt.Scale(domain=[_rho_min, _rho_max], nice=False, clamp=True),
        ),
        y2=alt.Y2("y_hi:Q"),
    ).properties(width=14, height=_fig2_height)

    _ticks = [-1.0, -0.5, 0.0, 0.5, 1.0]
    _tick_df = pd.DataFrame({
        "y": _ticks,
        "lbl": [f"{_t:+.1f}" if _t != 0 else "0.0" for _t in _ticks],
        "x": [1] * len(_ticks),
    })
    _tick_marks = alt.Chart(_tick_df).mark_text(
        align="right", baseline="middle",
        angle=0, fontSize=11, dx=-2,
    ).encode(
        x=alt.X("x:Q", axis=None,
                scale=alt.Scale(domain=[0, 1])),
        y=alt.Y(
            "y:Q", axis=None,
            scale=alt.Scale(domain=[_rho_min, _rho_max], nice=False, clamp=True),
        ),
        text="lbl:N",
    ).properties(width=24, height=_fig2_height)

    _title_mark = alt.Chart(pd.DataFrame({"t": ["Spearman ρ"]})).mark_text(
        align="center", baseline="middle",
        angle=270, fontSize=11,
    ).encode(text="t:N").properties(width=14, height=_fig2_height)

    _legend = alt.hconcat(_tick_marks, _grad, _title_mark, spacing=2)

    # Property-correlation dendrogram, drawn above the heatmap with
    # the same width (620) so the leaves line up with column centres.
    # Each U-shape from scipy is rendered as TWO vertical arms and
    # ONE horizontal top via `mark_rule` (axis-aligned segments) —
    # mark_line + detail/order produced no visible output in this
    # Altair build. Colour follows scipy's cluster-cut palette
    # (resolved from "C{N}" to explicit hex via ``_C_PALETTE``,
    # computed at the top of this cell so the dendrogram bars and the
    # heatmap's property-label colours stay in sync). The dashed red
    # rule marks the slider's |ρ| cutoff.
    # icoord[i] = [xL, xL, xR, xR]; dcoord[i] = [yLow_L, yTop, yTop, yLow_R].
    _vert_rows = []
    _horiz_rows = []
    for _i, (_xs, _ys, _col) in enumerate(zip(
        _dend["icoord"], _dend["dcoord"], _dend["color_list"],
    )):
        _c = _C_PALETTE.get(_col, _col)
        _vert_rows.append({"x": _xs[0], "y": _ys[0], "y2": _ys[1], "color": _c})
        _horiz_rows.append({"y": _ys[1], "x": _xs[1], "x2": _xs[2], "color": _c})
        _vert_rows.append({"x": _xs[3], "y": _ys[3], "y2": _ys[2], "color": _c})
    _vert_df = pd.DataFrame(_vert_rows)
    _horiz_df = pd.DataFrame(_horiz_rows)

    _n_props = len(_dend["leaves"])
    _ymax = (
        max([1.0] + [max(_ys) for _ys in _dend["dcoord"] if _ys])
        * 1.05
    )
    _x_scale = alt.Scale(domain=[0, 10 * _n_props], nice=False)
    _y_scale = alt.Scale(domain=[0, _ymax], nice=False)

    _vert_chart = alt.Chart(_vert_df).mark_rule(strokeWidth=1.2).encode(
        x=alt.X("x:Q", axis=None, scale=_x_scale),
        y=alt.Y("y:Q", axis=None, scale=_y_scale),
        y2=alt.Y2("y2:Q"),
        color=alt.Color("color:N", scale=None, legend=None),
    )
    _horiz_chart = alt.Chart(_horiz_df).mark_rule(strokeWidth=1.2).encode(
        x=alt.X("x:Q", axis=None, scale=_x_scale),
        x2=alt.X2("x2:Q"),
        y=alt.Y("y:Q", axis=None, scale=_y_scale),
        color=alt.Color("color:N", scale=None, legend=None),
    )
    _threshold_rule = alt.Chart(
        pd.DataFrame({"y": [_cut]})
    ).mark_rule(
        color="#C44E52", strokeDash=[4, 2], strokeWidth=1.0,
    ).encode(
        y=alt.Y("y:Q", axis=None, scale=_y_scale),
    )
    # Annotation positioned to the LEFT of the threshold rule. The
    # text anchor sits at the leftmost data x (=0) with ``align="right"``
    # so the text's right edge lands at x=0 and the body extends
    # leftward into the chart's outer padding. ``baseline="middle"``
    # centres the label vertically on the dashed rule. Vega-Lite
    # doesn't clip text marks by default, so the overflow renders.
    _threshold_label = alt.Chart(pd.DataFrame({
        "y": [_cut],
        "x": [0.0],
        "lbl": [f"Cluster threshold |ρ|>{_threshold:.2f}"],
    })).mark_text(
        align="right", baseline="middle",
        color="#C44E52", fontSize=9, dx=-3,
    ).encode(
        x=alt.X("x:Q", axis=None, scale=_x_scale),
        y=alt.Y("y:Q", axis=None, scale=_y_scale),
        text="lbl:N",
    )
    # Both the main figure title (text=) and the dendrogram subtitle
    # are attached directly to the dendrogram chart, which is exactly
    # 620 wide with no axis padding. Anchoring "middle" therefore
    # centres on the chart cells, not on the heatmap's wider bounding
    # box (which includes its left y-axis labels). The vconcat below
    # does NOT carry the title — that's how the previous version
    # ended up off-centre.
    _dendro_panel = (
        _vert_chart + _horiz_chart + _threshold_rule + _threshold_label
    ).properties(
        width=620, height=70,
        title=alt.TitleParams(
            text=(
                "Spearman ρ between each graph's structural property "
                "value and its layout-averaged metric value"
            ),
            anchor="middle",
            subtitle="Columns clustered by similarity of correlation pattern (average linkage)",
            subtitleFontSize=10,
            subtitleFontWeight="normal",
            subtitleColor="#555",
        ),
    )

    _dendro_and_heatmap = alt.vconcat(
        _dendro_panel, fig2_chart_copy, spacing=0,
    )

    # Push the legend down so its top lines up with the top of the
    # heatmap cells (not the top of the title/dendrogram block above
    # them). The spacer height covers title + subtitle + dendrogram.
    _LEGEND_TOP_OFFSET_PX = 68
    _legend_top_spacer = alt.Chart(
        pd.DataFrame({"_": [0]})
    ).mark_rect(opacity=0).properties(
        width=64, height=_LEGEND_TOP_OFFSET_PX,
    )
    _legend_padded = alt.vconcat(
        _legend_top_spacer, _legend, spacing=0,
    )

    fig2_chart_copy = alt.hconcat(
        _dendro_and_heatmap, _legend_padded, spacing=4,
    ).configure_view(stroke=None)
    save_chart_pdf(fig2_chart_copy, "fig2_bivariate_corr")
    fig2_chart_copy
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    Cell colour shows the Spearman correlation coefficient (rho) between each structural property and each readability metric, averaged across layouts for each graph. Blue indicates a positive association, while red indicates a negative one. The dendrogram groups properties with similar correlation patterns, using the dashed red cutoff to define the coloured clusters. This clustering determines the property order used in Figs. []. The thick horizontal line separates the eleven base metrics from the two composite scores.
    """)
    return


@app.cell(hide_code=True)
def _():
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.model_selection import train_test_split

    def fit_envelope_hgbr(X, y, random_state=0, test_size=0.2):
        """HGBR predicting an envelope statistic from properties on
        an 80/20 split. Returns the model + held-out X/y for
        downstream importance computation."""
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state
        )
        model = HistGradientBoostingRegressor(random_state=random_state)
        model.fit(X_train, y_train)
        return {
            "model": model,
            "X_test": X_test,
            "y_test": y_test,
            "r2_test": float(model.score(X_test, y_test)),
            "n_train": int(len(X_train)),
            "n_test": int(len(X_test)),
        }

    return (fit_envelope_hgbr,)


@app.cell(hide_code=True)
def _(
    METRICS,
    PROPERTIES,
    cluster_name,
    drawings,
    fit_envelope_hgbr,
    layout_clusters,
    np,
    pd,
    prop_clusters,
):
    # Variance partition for Fig 3 — per-drawing Shapley over the
    # property clusters (driven by the property-cluster slider) and
    # the layout choice. Layouts are encoded as **families** (using
    # the layout-cluster slider's grouping), not individual layouts,
    # so the layout block's Shapley value reflects the choice of
    # layout strategy rather than micro-variation within a family.
    # Recomputed when either slider moves (a few minutes per run).
    # All 17 retained structural properties — including
    # `degree_assortativity` — flow into the feature frame via
    # `_src[list(PROPERTIES)]`.
    _LAYOUT_LABEL = "Layout"
    _PER_DRAWING_SAMPLE_CAP = 60_000
    _N_PERMS_PER_DRAWING = 60

    # Map each property cluster's representative label → cluster size,
    # so we can show "Edge count (n=3)" for aggregates and just
    # "Edge count" for singletons on Fig 3's X axis. Built from the
    # currently-active prop_clusters dict so it tracks the slider.
    _members_by_cid = {}
    for _p, _cid in prop_clusters.items():
        _members_by_cid.setdefault(_cid, []).append(_p)
    _cluster_size_by_rep = {}
    for _cid, _members in _members_by_cid.items():
        _rep_label = cluster_name.get(_cid)
        if _rep_label is not None:
            _cluster_size_by_rep[_rep_label] = len(_members)

    def _augment_component(_row):
        if _row["kind"] != "cluster":
            return _row["component"]
        _n = _cluster_size_by_rep.get(_row["component"], 1)
        return _row["component"] if _n == 1 else f"{_row['component']} (n={_n})"

    _by_cid = {}
    for _p, _cid in prop_clusters.items():
        _by_cid.setdefault(_cid, []).append(_p)
    _cluster_cols = {
        cluster_name[_cid]: list(_props)
        for _cid, _props in _by_cid.items()
    }
    _rng = np.random.default_rng(0)
    if len(drawings) > _PER_DRAWING_SAMPLE_CAP:
        _idx = _rng.choice(
            len(drawings), _PER_DRAWING_SAMPLE_CAP, replace=False,
        )
        _src = drawings.iloc[_idx].reset_index(drop=True)
    else:
        _src = drawings.copy().reset_index(drop=True)

    # Map each layout to its family (cluster id) and one-hot the
    # family rather than the individual layout. Reduces correlated
    # within-family columns to one column per family, so the
    # "Layout" Shapley value reflects choice of strategy rather
    # than micro-variation within a family.
    _src_layout_family = _src["layout"].map(layout_clusters).fillna(-1).astype(int)
    _layout_dummies = pd.get_dummies(
        _src_layout_family.rename("layout_family"),
        prefix="layout_family", drop_first=False,
    ).astype(float)
    _feature_frame = pd.concat(
        [_src[list(PROPERTIES)], _layout_dummies], axis=1,
    )
    _layout_cols = list(_layout_dummies.columns)
    _feature_groups = {**_cluster_cols, _LAYOUT_LABEL: _layout_cols}
    _group_names = list(_feature_groups.keys())

    _rows = []
    _keys = list(METRICS) + ["quality", "empirical_quality"]
    for _metric in _keys:
        if _metric not in _src.columns:
            continue
        _y = _src[_metric]
        _mask = _feature_frame.notna().all(axis=1) & _y.notna()
        if int(_mask.sum()) < 100:
            continue
        _X = _feature_frame.loc[_mask]
        _yv = _y.loc[_mask]

        # R²(kept_cols) cache for this metric — Shapley over k
        # feature groups visits at most 2^k subsets across perms.
        _subset_r2 = {}
        def _r2_for(_cols_tuple):
            _key = frozenset(_cols_tuple)
            if _key in _subset_r2:
                return _subset_r2[_key]
            if not _cols_tuple:
                _subset_r2[_key] = 0.0
                return 0.0
            _fit = fit_envelope_hgbr(
                _X[list(_cols_tuple)], _yv,
            )
            _subset_r2[_key] = _fit["r2_test"]
            return _subset_r2[_key]

        _full_r2 = _r2_for(tuple(_X.columns))

        # Shapley sampling over feature groups (properties + layout).
        _perm_rng = np.random.default_rng(
            seed=(hash(_metric) & 0xFFFF) ^ 0xC0DE,
        )
        _sums = {_g: 0.0 for _g in _group_names}
        _counts = {_g: 0 for _g in _group_names}
        for _ in range(_N_PERMS_PER_DRAWING):
            _perm = list(_group_names)
            _perm_rng.shuffle(_perm)
            _prev_cols = ()
            _prev_r2 = 0.0
            for _g in _perm:
                _new_cols = _prev_cols + tuple(_feature_groups[_g])
                _new_r2 = _r2_for(_new_cols)
                _sums[_g] += _new_r2 - _prev_r2
                _counts[_g] += 1
                _prev_cols = _new_cols
                _prev_r2 = _new_r2
        _phi = {
            _g: (_sums[_g] / _counts[_g]) if _counts[_g] else 0.0
            for _g in _group_names
        }

        for _grp, _v in _phi.items():
            _rows.append({
                "metric": _metric, "component": _grp,
                "kind": ("layout" if _grp == _LAYOUT_LABEL else "cluster"),
                "share": float(_v), "full_r2": _full_r2,
            })
        _rows.append({
            "metric": _metric,
            "component": "Residual (not explained)",
            "kind": "residual", "share": 1.0 - _full_r2,
            "full_r2": _full_r2,
        })
    variance_partition_df = pd.DataFrame(_rows)
    if not variance_partition_df.empty:
        variance_partition_df["component"] = variance_partition_df.apply(
            _augment_component, axis=1,
        )
    return (variance_partition_df,)


@app.cell(hide_code=True)
def _(METRIC_LABEL, metric_leaf_order, variance_partition_df):
    # Metric Y-axis order for Figure 3 = metric-cluster leaf order
    # (slider-driven). Composites (`quality`, `empirical_quality`)
    # sit together at the end of the leaf order by design.
    _present = set(variance_partition_df["metric"])
    fig3_metric_order = [
        METRIC_LABEL.get(m, m)
        for m in metric_leaf_order
        if m in _present
    ]
    return


@app.cell(hide_code=True)
def _(
    METRICS,
    METRIC_LABEL,
    alt,
    cluster_name,
    metric_leaf_order,
    pd,
    prop_clusters,
    prop_leaf_order,
    save_chart_pdf,
    variance_partition_df,
):
    # Heatmap of metrics × (property cluster reps + Sum-of-property-
    # clusters + optional Layout + Residual).
    #
    # Per-cluster cells show **Shapley values** — the average marginal
    # contribution to held-out R² when that cluster joins a randomly-
    # ordered set of the other clusters. Shapley distributes shared
    # variance fairly across clusters that overlap, so the per-cell
    # numbers reflect total magnitude of explanation and sum (in
    # expectation) to R²_full. There is therefore no "Combined /
    # shared" column — its purpose under LOCO is subsumed.
    #
    # Column layout (left → right):
    #   ┌── property clusters (blue scale, one per cluster) ──┐
    #   ║ ⋮ DASHED-DOTTED VERTICAL RULE ⋮
    #   │ Sum of property clusters (left columns)             │
    #   │ Layout (if toggle ON, layouts encoded as families)  │ purple
    #   │ Residual  (=1 − R²_full)                            │
    #   └─────────────────────────────────────────────────────┘
    _CLUSTER_KIND = "cluster"
    _LAYOUT_KIND = "layout"
    # Layouts are encoded as families (clusters) in the Shapley
    # feature frame (see line ~1262 below), not as individual layout
    # dummies — so the axis tick should read "Layout family". The
    # variance attributable to within-family variation between
    # specific algorithms falls into Residual.
    _LAYOUT_LABEL = "Layout family"
    _SUM_PROPS_LABEL = "Sum of property clusters (left columns)"
    _RESIDUAL_LABEL = "Residual"

    # Property-cluster cells (blue scale).
    _cluster_df = variance_partition_df[
        variance_partition_df["kind"] == _CLUSTER_KIND
    ].copy()
    _cluster_df["metric_label"] = _cluster_df["metric"].map(METRIC_LABEL)
    _has_layout = (variance_partition_df["kind"] == _LAYOUT_KIND).any()

    # Purple-block cells: Sum of property clusters, optional Layout,
    # Residual.
    _purple_rows = []
    for _metric, _g in variance_partition_df.groupby("metric"):
        _full_r2 = float(_g["full_r2"].iat[0])
        _sum_unique_props = float(
            _g.loc[_g["kind"] == _CLUSTER_KIND, "share"].sum()
        )
        _layout_rows = _g.loc[_g["kind"] == _LAYOUT_KIND, "share"]
        _layout_share = float(_layout_rows.iat[0]) if len(_layout_rows) else None
        _resid_rows = _g.loc[_g["kind"] == "residual", "share"]
        _resid = float(_resid_rows.iat[0]) if len(_resid_rows) else 0.0
        _purple_rows.append({
            "metric": _metric, "component": _SUM_PROPS_LABEL,
            "share": _sum_unique_props, "full_r2": _full_r2,
        })
        if _layout_share is not None:
            _purple_rows.append({
                "metric": _metric, "component": _LAYOUT_LABEL,
                "share": _layout_share, "full_r2": _full_r2,
            })
        _purple_rows.append({
            "metric": _metric, "component": _RESIDUAL_LABEL,
            "share": _resid, "full_r2": _full_r2,
        })
    _purple_df = pd.DataFrame(_purple_rows)
    _purple_df["metric_label"] = _purple_df["metric"].map(METRIC_LABEL)

    # X-axis column order: property cluster reps (blue), then the
    # dashed-dotted vertical rule, then the purple block
    # (Sum first, Layout if present, Residual).
    _seen_cids = []
    _props_cluster_order = []
    _members_by_cid = {}
    for _p, _cid in prop_clusters.items():
        _members_by_cid.setdefault(_cid, []).append(_p)
    for _p in prop_leaf_order:
        _cid = prop_clusters.get(_p)
        if _cid is None or _cid in _seen_cids:
            continue
        _seen_cids.append(_cid)
        _rep_label = cluster_name[_cid]
        _n = len(_members_by_cid.get(_cid, ()))
        _props_cluster_order.append(
            _rep_label if _n == 1 else f"{_rep_label} (n={_n})"
        )
    _purple_block = [_SUM_PROPS_LABEL]
    if _has_layout:
        _purple_block.append(_LAYOUT_LABEL)
    _purple_block.append(_RESIDUAL_LABEL)
    _column_order = _props_cluster_order + _purple_block

    # Y axis: ALL metrics in leaf order (composites at the end).
    _present_metrics = (
        set(_cluster_df["metric"]) | set(_purple_df["metric"])
    )
    _metric_order_keys = [
        _m for _m in metric_leaf_order if _m in _present_metrics
    ]
    _metric_order_labels = [
        METRIC_LABEL.get(_m, _m) for _m in _metric_order_keys
    ]
    # Pandas Categorical forces the data row order to match the
    # leaf order. Vega-Lite's facet/categorical sort= argument has
    # been observed to silently fall back to alphabetical in
    # multi-layer charts; categorical sort_values is robust.
    _cluster_df["metric_label"] = pd.Categorical(
        _cluster_df["metric_label"],
        categories=_metric_order_labels, ordered=True,
    )
    _cluster_df = _cluster_df.sort_values(["metric_label", "component"])
    _purple_df["metric_label"] = pd.Categorical(
        _purple_df["metric_label"],
        categories=_metric_order_labels, ordered=True,
    )
    _purple_df = _purple_df.sort_values(["metric_label", "component"])

    # First composite metric — top of its band is the horizontal
    # separator between base metrics and composites.
    _composites_in_order = [
        _m for _m in _metric_order_keys if _m not in set(METRICS)
    ]
    _first_composite_label = (
        METRIC_LABEL.get(_composites_in_order[0])
        if _composites_in_order else None
    )

    # Colour-scale domains driven by the actual data range visible in
    # each group, so the legend's min/max match the chart's min/max
    # rather than fixed bounds. `_EPS` guards against degenerate domains
    # where min == max (e.g. all zeros).
    _EPS = 1e-6
    _cluster_share_min = float(_cluster_df["share"].min())
    _cluster_share_max = float(_cluster_df["share"].max())
    if _cluster_share_max - _cluster_share_min < _EPS:
        _cluster_share_max = _cluster_share_min + _EPS
    _cluster_share_mid = (_cluster_share_min + _cluster_share_max) / 2

    _purple_share_min = float(_purple_df["share"].min())
    _purple_share_max = float(_purple_df["share"].max())
    if _purple_share_max - _purple_share_min < _EPS:
        _purple_share_max = _purple_share_min + _EPS
    _purple_share_mid = (_purple_share_min + _purple_share_max) / 2

    _x_clusters = alt.X(
        "component:N", sort=_column_order,
        title=None,
        axis=alt.Axis(
            labelAngle=-45,
            labelLimit=300,
            labelFontSize=10,
            labelPadding=4,
        ),
    )
    _y = alt.Y(
        "metric_label:N", sort=_metric_order_labels,
        title="Readability metric",
        axis=alt.Axis(
            labelLimit=280,
            labelFontSize=11,
            labelPadding=4,
        ),
    )

    _cluster_heat = alt.Chart(_cluster_df).mark_rect(
        stroke="white", strokeWidth=0.5,
    ).encode(
        x=_x_clusters, y=_y,
        color=alt.Color(
            "share:Q",
            scale=alt.Scale(
                scheme="blues",
                domain=[_cluster_share_min, _cluster_share_max],
                clamp=True,
            ),
            legend=None,  # custom legend rendered below as a separate chart
        ),
        tooltip=[
            alt.Tooltip("metric_label:N", title="Metric"),
            alt.Tooltip("component:N", title="Property cluster"),
            alt.Tooltip("share:Q", format="+.2%", title="Shapley R²"),
            alt.Tooltip("full_r2:Q", format=".2f", title="Full R²"),
        ],
    )
    _cluster_text = alt.Chart(_cluster_df).mark_text(fontSize=9).encode(
        x=_x_clusters, y=_y,
        text=alt.Text("share:Q", format=".0%"),
        color=alt.condition(
            f"datum.share >= {_cluster_share_mid}",
            alt.value("white"), alt.value("#222"),
        ),
    )

    _purple_heat = alt.Chart(_purple_df).mark_rect(
        stroke="white", strokeWidth=0.5,
    ).encode(
        x=_x_clusters, y=_y,
        color=alt.Color(
            "share:Q",
            scale=alt.Scale(
                scheme="purples",
                domain=[_purple_share_min, _purple_share_max],
                clamp=True,
            ),
            legend=None,  # custom legend rendered below as a separate chart
        ),
        tooltip=[
            alt.Tooltip("metric_label:N", title="Metric"),
            alt.Tooltip("component:N", title="Component"),
            alt.Tooltip("share:Q", format="+.2%", title="R² share"),
        ],
    )
    _purple_text = alt.Chart(_purple_df).mark_text(fontSize=9).encode(
        x=_x_clusters, y=_y,
        text=alt.Text("share:Q", format=".0%"),
        color=alt.condition(
            f"datum.share >= {_purple_share_mid}",
            alt.value("white"), alt.value("#222"),
        ),
    )

    # Dashed-dotted vertical separator between the property-cluster
    # block (blue) and the purple block (Sum + Layout + Residual).
    # Anchored to the LEFT edge of `Sum of property clusters (left
    # columns)` via bandPosition=0.
    _vrule = alt.Chart(
        pd.DataFrame({"component": [_SUM_PROPS_LABEL]})
    ).mark_rule(
        stroke="#222", strokeWidth=2.5,
        strokeDash=[6, 3, 1, 3],  # dash-dot pattern
    ).encode(
        x=alt.X(
            "component:N", sort=_column_order,
            bandPosition=0,
        ),
    )

    # Horizontal separator between base metrics and composites,
    # anchored to the TOP edge of the first composite row.
    if _first_composite_label is not None:
        _hrule = alt.Chart(
            pd.DataFrame({"metric_label": [_first_composite_label]})
        ).mark_rule(stroke="#222", strokeWidth=3).encode(
            y=alt.Y(
                "metric_label:N", sort=_metric_order_labels,
                bandPosition=0,
            ),
        )
    else:
        _hrule = None

    # `+` chaining (not `alt.layer(*)`) so the heatmap's Y / X axis
    # encodings (with labels) are canonical and the rule layers
    # don't strip them.
    _heatmap = (
        _cluster_heat + _cluster_text + _purple_heat + _purple_text
    )
    fig3_chart = (_heatmap + _vrule)
    if _hrule is not None:
        fig3_chart = fig3_chart + _hrule

    # Match the legend stack height to the heatmap's vertical extent:
    # one Step(28) row per metric label, summed.
    _row_step_px = 28
    _heatmap_height_px = _row_step_px * len(_metric_order_labels)
    fig3_chart = fig3_chart.properties(
        width=alt.Step(64),
        height=_heatmap_height_px,
    ).resolve_scale(color="independent")

    # Custom color legends — built from mark_rect (gradient) + mark_text
    # (tick labels on the inside next to the gradient, descriptive title
    # rotated on the outside) so we can match the heatmap height pixel-
    # for-pixel and rotate text freely (alt.Legend doesn't expose
    # labelAngle / titleAngle). A single rect with a linear-gradient
    # fill avoids the hairline gaps that a stack of discrete colour
    # rects would produce on the SVG renderer.
    _BLUES_STOPS = [
        "#f7fbff", "#deebf7", "#c6dbef", "#9ecae1", "#6baed6",
        "#4292c6", "#2171b5", "#08519c", "#08306b",
    ]
    _PURPLES_STOPS = [
        "#fcfbfd", "#efedf5", "#dadaeb", "#bcbddc", "#9e9ac8",
        "#807dba", "#6a51a3", "#54278f", "#3f007d",
    ]

    def _make_legend_panel(_stops, _vmin, _vmax, _height_px, _title_text):
        # Linear-gradient stops mirror the d3 Blues / Purples schemes
        # used by the heatmap, so the colour at any height on the
        # legend matches the colour the heatmap assigns to the same
        # share value. Domain = [vmin, vmax] of the actual data, so
        # the legend reflects the visualisation rather than fixed bounds.
        _grad_stops = [
            {"offset": _i / (len(_stops) - 1), "color": _c}
            for _i, _c in enumerate(_stops)
        ]
        _grad = alt.Chart(pd.DataFrame({
            "x_lo": [0], "x_hi": [1],
            "y_lo": [_vmin], "y_hi": [_vmax],
        })).mark_rect(
            color={
                "gradient": "linear",
                "x1": 0, "x2": 0,
                "y1": 1, "y2": 0,  # offset 0 = bottom (light), 1 = top (dark)
                "stops": _grad_stops,
            },
        ).encode(
            x=alt.X("x_lo:Q", axis=None,
                    scale=alt.Scale(domain=[0, 1])),
            x2=alt.X2("x_hi:Q"),
            y=alt.Y(
                "y_lo:Q", axis=None,
                scale=alt.Scale(domain=[_vmin, _vmax], nice=False, clamp=True),
            ),
            y2=alt.Y2("y_hi:Q"),
        ).properties(width=14, height=_height_px)

        # Tick labels on the INSIDE of the gradient (between gradient
        # and heatmap), right-aligned to the panel's right edge so
        # they sit flush against the gradient. Horizontal so the
        # percentages read normally. Five evenly-spaced ticks span the
        # actual [vmin, vmax] range.
        _ticks = [_vmin + (_vmax - _vmin) * _i / 4 for _i in range(5)]
        _tick_df = pd.DataFrame({
            "y": _ticks,
            # Collapse "-0%" (a small negative that rounds to zero
            # under .0f) onto a plain "0%" so the legend never shows a
            # signed zero. Genuine non-zero values keep their natural
            # sign.
            "lbl": [
                "0%" if round(_t * 100) == 0 else f"{_t * 100:.0f}%"
                for _t in _ticks
            ],
            "x": [1] * len(_ticks),
        })
        _tick_marks = alt.Chart(_tick_df).mark_text(
            align="right", baseline="middle",
            angle=0, fontSize=11, dx=-2,
        ).encode(
            x=alt.X("x:Q", axis=None,
                    scale=alt.Scale(domain=[0, 1])),
            y=alt.Y(
                "y:Q", axis=None,
                scale=alt.Scale(domain=[_vmin, _vmax], nice=False, clamp=True),
            ),
            text="lbl:N",
        ).properties(width=30, height=_height_px)

        # Descriptive title on the OUTSIDE, rotated 270° (reads
        # bottom-to-top). fontSize=11 matches the heatmap's y-axis
        # labelFontSize so the legend type sizes with the rest of
        # the chart.
        _title_df = pd.DataFrame({"t": [_title_text]})
        _title_mark = alt.Chart(_title_df).mark_text(
            align="center", baseline="middle",
            angle=270, fontSize=11,
        ).encode(text="t:N").properties(width=16, height=_height_px)

        return alt.hconcat(_tick_marks, _grad, _title_mark, spacing=2)

    _legend_spacing = 14
    _legend_panel_h = (_heatmap_height_px - _legend_spacing) // 2
    _blue_legend = _make_legend_panel(
        _BLUES_STOPS, _cluster_share_min, _cluster_share_max,
        _legend_panel_h, "Property cluster unique R²",
    )
    _purple_legend = _make_legend_panel(
        _PURPLES_STOPS, _purple_share_min, _purple_share_max,
        _legend_panel_h,
        "Sum of properties / layout / residual R²",
    )
    _legend_stack = alt.vconcat(
        _blue_legend, _purple_legend, spacing=_legend_spacing,
    )

    # Title on the heatmap (not the outer hconcat) so it centres on the
    # heatmap width rather than heatmap+legend width.
    fig3_chart = fig3_chart.properties(
        title=alt.TitleParams(
            text=(
                "Shapley R² contribution of each property cluster "
                "to each readability metric"
            ),
            anchor="middle",
        ),
    )
    fig3_chart = alt.hconcat(
        fig3_chart, _legend_stack, spacing=4,
    ).configure_view(stroke=None)
    save_chart_pdf(fig3_chart, "fig3_shapley_partition")
    fig3_chart
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    Each row shows a Shapley-value variance split for one readability metric. The blue cells, to the left of the dashed line, show the average contribution of each structural property cluster to held-out R², computed across different orderings of the other clusters. Larger values indicate that the cluster carries more predictive signal; when clusters are correlated, they share credit. The purple cells sum these cluster contributions, add the layout effect, and show the remaining unexplained variance. Layouts are grouped by family rather than by individual algorithm [section reference]. The thick horizontal line separates the eleven base metrics from the two composite scores.
    """)
    return


@app.cell(hide_code=True)
def _():
    N_BINS_OPTIONS = tuple(range(3, 11))
    return (N_BINS_OPTIONS,)


@app.cell(hide_code=True)
def _(METRICS_PLUS, N_BINS_OPTIONS, PROPERTIES, envelope_table, np, pd):
    # Pre-computed `pd.qcut` bundles keyed by n_bins ∈ {3..10}. Each
    # (property, metric, bin) row carries the min / max / median of
    # the metric's envelope-mean within that bin plus the full-corpus
    # min / max for reference. Building all 8 bundles up-front means
    # the n_bins slider only triggers a dict lookup downstream.
    def _build_qcut(_n_bins):
        _rows = []
        for _prop in PROPERTIES:
            _x = envelope_table[_prop].astype(float)
            for _metric in METRICS_PLUS:
                _target = f"{_metric}_mean"
                if _target not in envelope_table.columns:
                    continue
                _y = envelope_table[_target]
                _mask = _x.notna() & _y.notna()
                if int(_mask.sum()) < 100:
                    continue
                _xm = _x[_mask]
                _ym = _y[_mask]
                _full_min = float(_ym.min())
                _full_max = float(_ym.max())
                _full_range = _full_max - _full_min
                if _full_range == 0:
                    continue
                try:
                    _bins = pd.qcut(
                        _xm, _n_bins, duplicates="drop", labels=False,
                    )
                except ValueError:
                    continue
                _actual = int(_bins.max()) + 1 if len(_bins) else 0
                for _b in range(_actual):
                    _bm = (_bins == _b)
                    if int(_bm.sum()) < 10:
                        continue
                    _yb = _ym[_bm]
                    _xb = _xm[_bm]
                    _rows.append({
                        "property": _prop, "metric": _metric,
                        "bin": int(_b),
                        "bin_label": f"Q{int(_b) + 1}",
                        "x_p25": float(np.percentile(_xb, 25)),
                        "x_median": float(_xb.median()),
                        "x_p75": float(np.percentile(_xb, 75)),
                        "y_min": float(_yb.min()),
                        "y_max": float(_yb.max()),
                        "y_median": float(_yb.median()),
                        "n_in_bin": int(_bm.sum()),
                        "full_y_min": _full_min,
                        "full_y_max": _full_max,
                        "full_y_range": _full_range,
                    })
        return pd.DataFrame(_rows)

    conditional_envelope_qcut_bundles = {
        _nb: _build_qcut(_nb) for _nb in N_BINS_OPTIONS
    }
    return (conditional_envelope_qcut_bundles,)


@app.cell(hide_code=True)
def _(METRICS_PLUS, N_BINS_OPTIONS, PROPERTIES, envelope_table, np, pd):
    # Equal-width (`pd.cut`) companion bundles. Same schema as the qcut
    # bundle, so the chart cell can swap between them via a dict lookup.
    # Equal-width bins span equal *ranges* of property value, so
    # heavy-tailed properties will produce sparse / empty high-end bins
    # — the honest picture of where graphs actually live in property
    # space.
    def _build_cut(_n_bins):
        _rows = []
        for _prop in PROPERTIES:
            _x = envelope_table[_prop].astype(float)
            for _metric in METRICS_PLUS:
                _target = f"{_metric}_mean"
                if _target not in envelope_table.columns:
                    continue
                _y = envelope_table[_target]
                _mask = _x.notna() & _y.notna()
                if int(_mask.sum()) < 100:
                    continue
                _xm = _x[_mask]
                _ym = _y[_mask]
                _full_min = float(_ym.min())
                _full_max = float(_ym.max())
                _full_range = _full_max - _full_min
                if _full_range == 0 or float(_xm.max()) == float(_xm.min()):
                    continue
                try:
                    _bins = pd.cut(
                        _xm, bins=_n_bins, labels=False, include_lowest=True,
                    )
                except ValueError:
                    continue
                for _b in range(_n_bins):
                    _bm = (_bins == _b)
                    if int(_bm.sum()) < 10:
                        continue
                    _yb = _ym[_bm]
                    _xb = _xm[_bm]
                    _rows.append({
                        "property": _prop, "metric": _metric,
                        "bin": int(_b),
                        "bin_label": f"B{_b + 1}",
                        "x_p25": float(np.percentile(_xb, 25)),
                        "x_median": float(_xb.median()),
                        "x_p75": float(np.percentile(_xb, 75)),
                        "y_min": float(_yb.min()),
                        "y_max": float(_yb.max()),
                        "y_median": float(_yb.median()),
                        "n_in_bin": int(_bm.sum()),
                        "full_y_min": _full_min,
                        "full_y_max": _full_max,
                        "full_y_range": _full_range,
                    })
        return pd.DataFrame(_rows)

    conditional_envelope_cut_bundles = {
        _nb: _build_cut(_nb) for _nb in N_BINS_OPTIONS
    }
    return (conditional_envelope_cut_bundles,)


@app.cell(hide_code=True)
def _(METRICS_PLUS, METRIC_LABEL, PROPERTIES, PROPERTY_LABEL, mo):
    n_bins_slider = mo.ui.slider(
        start=3, stop=10, step=1, value=10,
        label="Number of bins (n)", show_value=True,
    )
    binning_toggle = mo.ui.switch(
        value=True,
        label="Equal-width bins by property value (off = equal-count / quintile-style)",
    )
    # Multiselects start with every option selected; un-ticking an
    # option drops that row (metric) or column (property) from Fig 4.
    # `value=` is the list of *option keys* (display labels), not the
    # backing values — marimo looks each entry up in `options` to
    # resolve the initial selection.
    _property_options = {PROPERTY_LABEL.get(p, p): p for p in PROPERTIES}
    _metric_options = {METRIC_LABEL.get(m, m): m for m in METRICS_PLUS}
    # Defaults reproduce the paper's Figure 4: one representative
    # property per structural cluster and metrics spanning the
    # graph-dominated / layout-dominated / residual-heavy groups.
    # Add or remove entries interactively to explore the full matrix.
    _paper_properties = [
        "Crossing-number lower bound",
        "Mean local clustering",
        "Mean degree",
        "Diameter",
        "Mean shortest path",
        "Degree assortativity",
        "Node count",
        "Edge count",
    ]
    _paper_metrics = [
        "Edge orthogonality",
        "Node–edge occlusion",
        "Crossing angle",
        "Angular resolution",
        "Edge crossings",
        "Neighbourhood preservation",
        "Edge length deviation",
        "Empirical quality (3-metric)",
    ]
    property_filter = mo.ui.multiselect(
        options=_property_options,
        value=_paper_properties,
        label="Properties (uncheck to hide column)",
    )
    metric_filter = mo.ui.multiselect(
        options=_metric_options,
        value=_paper_metrics,
        label="Metrics (uncheck to hide row)",
    )
    return binning_toggle, metric_filter, n_bins_slider, property_filter


@app.cell(hide_code=True)
def _(binning_toggle, metric_filter, mo, n_bins_slider, property_filter):
    mo.vstack([
        n_bins_slider,
        binning_toggle,
        property_filter,
        metric_filter,
    ])
    return


@app.cell(hide_code=True)
def _(
    binning_toggle,
    conditional_envelope_cut_bundles,
    conditional_envelope_qcut_bundles,
    n_bins_slider,
):
    # Resolve the slider + toggle into a single dataframe pick. Two
    # caption strings let the chart subtitle stay self-describing in
    # static exports.
    selected_n_bins = int(n_bins_slider.value)
    if binning_toggle.value:
        selected_envelope_df = conditional_envelope_cut_bundles[selected_n_bins]
        selected_binning_label = (
            f"equal-width by property value (n={selected_n_bins})"
        )
        selected_bin_axis_caption = (
            f"Equal-width bin (B1 = lowest property values → "
            f"B{selected_n_bins} = highest)"
        )
    else:
        _pct = round(100 / selected_n_bins, 1)
        selected_envelope_df = (
            conditional_envelope_qcut_bundles[selected_n_bins]
        )
        selected_binning_label = (
            f"equal-count (quintile-style, n={selected_n_bins})"
        )
        selected_bin_axis_caption = (
            f"Equal-count bin (Q1 = lowest {_pct:.1f}% → "
            f"Q{selected_n_bins} = highest {_pct:.1f}%)"
        )
    return selected_envelope_df, selected_n_bins


@app.cell(hide_code=True)
def _(
    METRIC_LABEL_WRAPPED,
    PROPERTY_LABEL_COMPACT,
    alt,
    metric_filter,
    metric_leaf_order,
    mo,
    pd,
    prop_leaf_order,
    property_filter,
    selected_envelope_df,
    selected_n_bins,
):
    # Build the ribbon matrix from the slider-selected envelope bundle.
    # Fig 4 is a descriptive visualisation (no model with collinearity
    # issues), so we show ALL metrics on Y and ALL properties on X —
    # no cluster-rep collapsing. The dendrograms upstream still convey
    # the clustering structure for anyone who wants it.
    LOW_N_THRESHOLD = 1000
    _df = selected_envelope_df.copy()

    # Apply the property/metric multiselect filters. Multiselects start
    # with every option selected; un-ticking removes the row or column
    # from the matrix without rebuilding any cached bundle.
    _selected_props = set(property_filter.value or [])
    _selected_metrics = set(metric_filter.value or [])
    _df = _df[
        _df["property"].isin(_selected_props)
        & _df["metric"].isin(_selected_metrics)
    ]

    if _df.empty:
        fig4_chart = mo.md(
            "_No data to display — select at least one property and one "
            "metric in the controls above._"
        )
    else:
        _df["metric_label"] = (
            _df["metric"].map(METRIC_LABEL_WRAPPED).fillna(_df["metric"])
        )
        _df["property_label"] = (
            _df["property"].map(PROPERTY_LABEL_COMPACT).fillna(_df["property"])
        )
        _df["bin_idx"] = _df["bin"].astype(int) + 1

        _prop_order = [
            PROPERTY_LABEL_COMPACT.get(_p, _p) for _p in prop_leaf_order
            if _p in set(_df["property"])
        ]
        # Metric Y-axis order = full leaf order (base first, composites
        # at the end). Pandas Categorical forces the underlying data row
        # order; altair's facet `sort=` is unreliable for ~13-row
        # layered cells (observed empirically), so categorical
        # sort_values is the robust path.
        _present_keys = set(_df["metric"])
        _metric_order_keys = [
            _m for _m in metric_leaf_order if _m in _present_keys
        ]
        _metric_order = [
            METRIC_LABEL_WRAPPED.get(_m, _m) for _m in _metric_order_keys
        ]
        _df["metric_label"] = pd.Categorical(
            _df["metric_label"], categories=_metric_order, ordered=True,
        )
        _df = (
            _df.sort_values(["metric_label", "property_label", "bin_idx"])
            .reset_index(drop=True)
        )

        # Per-bin x extents so mark_rect can draw one rectangle per bin.
        # mark_area smears colour across bins (one fill per group), so
        # the low-n highlight wouldn't show. mark_rect with x/x2 honours
        # the per-row colour condition.
        _df["x_lo"] = _df["bin_idx"] - 0.5
        _df["x_hi"] = _df["bin_idx"] + 0.5

        _x = alt.X(
            "bin_idx:Q", axis=None,
            scale=alt.Scale(domain=[0.5, selected_n_bins + 0.5]),
        )
        _y_scale = alt.Scale(domain=[0, 1], nice=False, clamp=True)

        # Row header — full metric names rotated -90° (read bottom-to-
        # top). The `labelExpr=split(...)` step forces Vega-Lite to
        # treat the label as an array of lines so embedded \n in
        # METRIC_LABEL_WRAPPED renders as a hard line break rather
        # than a literal character. labelPadding sits close to the
        # cell edge.
        _row_header = alt.Header(
            orient="left",
            labelAngle=-90,
            labelAlign="center",
            labelBaseline="middle",
            labelLimit=140,
            labelPadding=2,
            labelFontSize=11,
            labelLineHeight=12,
            labelExpr="split(datum.label, '\\n')",
        )
        # Column header — property labels parallel to the x axis.
        # Same split() trick so multi-word PROPERTY_LABEL_COMPACT
        # entries render across multiple lines that fit the cell width.
        # Negative labelPadding pulls the labels right down onto the
        # cell tops (a positive value would push them away).
        _col_header = alt.Header(
            orient="top",
            labelAngle=0,
            labelAlign="center",
            labelBaseline="bottom",
            labelLimit=120,
            labelPadding=-4,
            labelFontSize=10,
            labelLineHeight=11,
            labelExpr="split(datum.label, '\\n')",
        )

        # Color condition: orange when a bin's n_in_bin is below
        # LOW_N_THRESHOLD (the estimate is statistically weak so the
        # cell visually flags the warning).
        _low_n_expr = f"datum.n_in_bin < {LOW_N_THRESHOLD}"
        _ribbon_color = alt.condition(
            _low_n_expr, alt.value("#E08436"), alt.value("#3B6FB6"),
        )
        _line_dot_color = alt.condition(
            _low_n_expr, alt.value("#C25B12"), alt.value("#1B3D6E"),
        )

        def _build_facet(_df_part, _metric_order_part, _show_col_header, _spacing=6):
            # One layered ribbon-and-line panel per (metric × property),
            # faceted by row=metric, column=property. Marks colour-coded
            # orange when the bin's n_in_bin < LOW_N_THRESHOLD.
            _b = alt.Chart(_df_part)
            _bg_max = _b.mark_rule(
                strokeDash=[2, 3], color="#D5D5D5", strokeWidth=0.7,
            ).encode(y=alt.Y("full_y_max:Q", scale=_y_scale, axis=None))
            _bg_min = _b.mark_rule(
                strokeDash=[2, 3], color="#D5D5D5", strokeWidth=0.7,
            ).encode(y=alt.Y("full_y_min:Q", scale=_y_scale, axis=None))
            # Per-bin filled boxes — colour condition can flip individual
            # bins to orange (mark_area renders one fill per data group,
            # so per-row colour condition wouldn't work there).
            _box = _b.mark_rect(opacity=0.40, stroke=None).encode(
                x=alt.X("x_lo:Q", axis=None,
                        scale=alt.Scale(domain=[0.5, selected_n_bins + 0.5])),
                x2=alt.X2("x_hi:Q"),
                y=alt.Y("y_min:Q", scale=_y_scale, axis=None),
                y2=alt.Y2("y_max:Q"),
                color=_ribbon_color,
            )
            # Per-bin "max line" — mark_rule from x_lo to x_hi at y_max.
            # Each bin's segment is independently coloured, so the line
            # picks up the orange highlight on low-n bins just like the
            # ribbon does. Continuous mark_line wouldn't allow per-segment
            # colouring (single colour per line group).
            _ln = _b.mark_rule(strokeWidth=2.0).encode(
                x=alt.X("x_lo:Q", axis=None,
                        scale=alt.Scale(domain=[0.5, selected_n_bins + 0.5])),
                x2=alt.X2("x_hi:Q"),
                y=alt.Y("y_max:Q", scale=_y_scale, axis=None),
                color=_line_dot_color,
            )
            _dt = _b.mark_point(size=16, filled=True, opacity=0.95).encode(
                x=_x, y=alt.Y("y_median:Q", scale=_y_scale, axis=None),
                color=_line_dot_color,
            )
            _layers = [_bg_min, _bg_max, _box, _ln, _dt]
            _cell_part = _layers[0]
            for _layer in _layers[1:]:
                _cell_part = _cell_part + _layer
            _cell_part = _cell_part.properties(width=84, height=62)
            return _cell_part.facet(
                row=alt.Row(
                    "metric_label:N", sort=_metric_order_part,
                    title=None, header=_row_header,
                ),
                column=alt.Column(
                    "property_label:N", sort=_prop_order, title=None,
                    header=(_col_header if _show_col_header
                            else alt.Header(labels=False, title=None)),
                ),
                spacing=_spacing,
            ).resolve_scale(y="shared")

        fig4_chart = _build_facet(
            _df, _metric_order, _show_col_header=True, _spacing=6,
        ).properties(
            title=alt.TitleParams(
                text=(
                    f"Readability metric ranges across structural-property "
                    f"bins (equal-width, n={selected_n_bins})"
                ),
                anchor="middle",
            ),
        )
    # No auto-save here — Fig 4 is filter-driven and the cell would
    # otherwise overwrite the PDF with the default all-columns /
    # all-rows view on every initial load. The dedicated save-button
    # cell at the bottom of the notebook saves the current filtered
    # state on demand.
    fig4_chart
    return (fig4_chart,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    Each cell shows how one readability metric varies across equal-width bins of a structural property. The ribbon shows the per-bin range from minimum to maximum, the heavy line marks the per-bin maximum (metric ceiling), and the dot marks the median. Grey dotted horizontal lines show the minimum and maximum metric values observed across the full set of 1M+ drawings. When the upper boundary slopes across a cell, it indicates a structure-driven limit: in that region, graphs cannot achieve higher metric values regardless of the layout chosen. Bins with fewer than 1,000 graphs are shown in orange to flag weaker statistical support.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ### Save Fig 4 with current selection

    Click the button to write the **currently displayed** Fig 4 — i.e.
    the equal-width binned readability matrix restricted to the bins,
    properties, and metrics chosen in the controls above — to
    `<EXPORT_DIR>/fig4_envelope_matrix.pdf`. The save is gated by the
    button so the PDF only updates when you explicitly ask, rather
    than being overwritten with the full default view every time the
    cell re-evaluates.
    """)
    return


@app.cell
def _(mo):
    save_fig4_button = mo.ui.run_button(
        label="Save Fig 4 with current bins / properties / metrics",
    )
    save_fig4_button
    return (save_fig4_button,)


@app.cell(hide_code=True)
def _(fig4_chart, mo, save_chart_pdf, save_fig4_button):
    # `mo.ui.run_button.value` is True only on the click that
    # triggered this cell's re-evaluation, so the save fires once per
    # press rather than every time fig4_chart is recomputed. The
    # `to_dict` duck-type check guards the empty-filter branch, where
    # fig4_chart is an mo.md placeholder rather than an Altair spec.
    # In headless script mode (``python paper_visualisations.py``)
    # there is no button to press, so the default (paper) selection
    # is saved unconditionally.
    _headless = mo.app_meta().mode == "script"
    if (save_fig4_button.value or _headless) and hasattr(fig4_chart, "to_dict"):
        save_chart_pdf(fig4_chart, "fig4_envelope_matrix")
    return


if __name__ == "__main__":
    app.run()
