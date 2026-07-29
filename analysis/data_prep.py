"""Shared data loaders for the analysis notebooks.

Builds two canonical frames from a pipeline output directory:

- ``drawings``: long-form, one row per (graph_id, layout) with the 11
  metric columns, the 24 structural properties, and cohort/source.
  The frame carries a ``layout`` column (the algorithm id) but NOT a
  pre-computed family grouping — notebooks that want a theory-based
  grouping define it inline; notebooks that want an empirical
  grouping run the cluster-slider machinery in
  ``paper_visualisations.py``.
- ``envelopes``: one row per graph with `<metric>_min`,
  `<metric>_max`, `<metric>_range` columns merged onto manifest.

Caches both as parquet under ``analysis/cache/`` (legacy single-output
API) or ``<pipeline_dir>/.analysis_cache/`` (directory-aware API) so
re-loads are cheap across notebooks.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PIPELINE_DIR = Path(__file__).resolve().parent / "data"
MANIFEST_CSV = PIPELINE_DIR / "manifest.csv"
METRICS_DIR = PIPELINE_DIR / "metrics"
TIMINGS_DIR = PIPELINE_DIR / "_timings"

CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

LAYOUTS = [
    "FMMM",
    "HOLA",
    "arc-bfs",
    "circular",
    "curated",
    "dot-ortho",
    "drgraph",
    "forceatlas2",
    "fruchterman-reingold",
    "kamada-kawai",
    "pivot-MDS",
    "planar",
    "planarization-ortho",
    "radial-tree",
    "random",
    "sfdp",
    "spectral",
    "stress-majorization",
    "sugiyama",
]

ALGORITHMIC_LAYOUTS = [layout for layout in LAYOUTS if layout != "curated"]
CURATOR_LAYOUTS = ["curated"]

METRICS = [
    "angular_resolution",
    "aspect_ratio",
    "crossing_angle",
    "edge_crossings",
    "edge_length_deviation",
    "edge_orthogonality",
    "kruskal_stress",
    "neighbourhood_preservation",
    "node_edge_occlusion",
    "node_resolution",
    "node_uniformity",
]

STRUCTURAL_PROPERTIES = [
    "n_nodes",
    "n_edges",
    "density",
    "is_bipartite",
    "is_planar",
    "is_tree",
    "is_forest",
    "is_regular",
    "is_eulerian",
    "min_degree",
    "max_degree",
    "mean_degree",
    "degree_std",
    "diameter",
    "radius",
    "avg_shortest_path_length",
    "n_triangles",
    "average_clustering",
    "transitivity",
    "degree_assortativity",
    "n_biconnected_components",
    "degeneracy",
    "crossing_number_lb_euler",
    "crossing_number_lb_bipartite",
]

COHORTS = ["generated", "calibration", "benchmark", "real_world", "graphs_with_drawings"]

# NOTE: The hardcoded theory-based `LAYOUT_FAMILY` map used to live
# here and was added to the loaded drawings frame as a `layout_family`
# column. It was removed because:
#   - The active notebooks (paper / appendix / exploratory) now group
#     layouts by *empirical* clusters (Spearman ρ on the per-graph
#     quality vector cut at a slider threshold), not by hand-curated
#     theory families. The cluster names live in the notebooks that
#     use them, not in the loader.
#   - The hardcoded map silently fell back to "Other" for any layout
#     id it didn't recognise, which masked typos and the addition of
#     new layouts (e.g. drgraph, forceatlas2, sfdp).
# If a notebook still needs a theory-based grouping, define the dict
# inline in that notebook and `.map()` it onto the `layout` column.


def load_manifest(refresh: bool = False) -> pd.DataFrame:
    cache = CACHE_DIR / "manifest.parquet"
    if cache.exists() and not refresh:
        return pd.read_parquet(cache)
    manifest = pd.read_csv(MANIFEST_CSV)
    manifest.to_parquet(cache)
    return manifest


def load_drawings(refresh: bool = False) -> pd.DataFrame:
    """Long-form drawings frame: one row per (graph_id, layout)."""
    cache = CACHE_DIR / "drawings.parquet"
    if cache.exists() and not refresh:
        return pd.read_parquet(cache)

    manifest = load_manifest(refresh=refresh)
    parts = []
    for layout in LAYOUTS:
        path = METRICS_DIR / f"{layout}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if df.empty:
            continue
        df["layout"] = layout
        parts.append(df)

    drawings = pd.concat(parts, ignore_index=True)
    drawings = drawings.merge(manifest, on="graph_id", how="left")
    drawings.to_parquet(cache)
    return drawings


def load_envelopes(refresh: bool = False) -> pd.DataFrame:
    """Per-graph envelope frame: one row per graph_id with `_min`, `_max`,
    `_range` columns for each metric, plus all structural properties."""
    cache = CACHE_DIR / "envelopes.parquet"
    if cache.exists() and not refresh:
        return pd.read_parquet(cache)

    drawings = load_drawings(refresh=refresh)
    agg = drawings.groupby("graph_id")[METRICS].agg(["min", "max"])
    agg.columns = [f"{m}_{stat}" for m, stat in agg.columns]
    for m in METRICS:
        agg[f"{m}_range"] = agg[f"{m}_max"] - agg[f"{m}_min"]
    agg["n_drawings"] = drawings.groupby("graph_id").size()
    agg = agg.reset_index()

    manifest = load_manifest(refresh=refresh)
    envelopes = agg.merge(manifest, on="graph_id", how="left")
    envelopes.to_parquet(cache)
    return envelopes


def load_metric_timings(refresh: bool = False) -> pd.DataFrame:
    cache = CACHE_DIR / "metric_timings.parquet"
    if cache.exists() and not refresh:
        return pd.read_parquet(cache)
    df = pd.read_csv(TIMINGS_DIR / "metrics.csv")
    df.to_parquet(cache)
    return df


def load_property_timings(refresh: bool = False) -> pd.DataFrame:
    cache = CACHE_DIR / "property_timings.parquet"
    if cache.exists() and not refresh:
        return pd.read_parquet(cache)
    df = pd.read_csv(TIMINGS_DIR / "properties.csv")
    df.to_parquet(cache)
    return df


def quality_score(drawings: pd.DataFrame) -> pd.Series:
    """Composite quality = mean of the 11 metrics, ignoring NaNs."""
    return drawings[METRICS].mean(axis=1, skipna=True)


def cohort_palette() -> dict[str, str]:
    return {
        "generated": "#4C72B0",
        "calibration": "#DD8452",
        "benchmark": "#55A467",
        "real_world": "#C44E52",
        "graphs_with_drawings": "#8172B3",
    }


# --------------------------------------------------------------------- #
# Directory-aware loaders (preferred for new notebooks).
#
# These take a ``pipeline_dir`` explicitly, discover available layouts
# from ``<pipeline_dir>/metrics/*.csv`` rather than from the hardcoded
# ``LAYOUTS`` list, and place the parquet cache at
# ``<pipeline_dir>/.analysis_cache/`` so it travels with the data and
# isn't shared between different pipeline outputs.
#
# Notebook usage:
#
#     from data_prep import load_corpus
#     PIPELINE_DIR = Path(__file__).resolve().parent / "data"
#     manifest, drawings = load_corpus(PIPELINE_DIR)
# --------------------------------------------------------------------- #


def _dir_cache(pipeline_dir: Path, name: str) -> Path:
    return Path(pipeline_dir) / ".analysis_cache" / f"{name}.parquet"


def discover_layouts(pipeline_dir) -> list[str]:
    """Return the sorted list of layout names found in
    ``<pipeline_dir>/metrics/*.csv``. Layout name = CSV filename
    without the ``.csv`` extension."""
    metrics_dir = Path(pipeline_dir) / "metrics"
    if not metrics_dir.is_dir():
        raise FileNotFoundError(
            f"Expected a metrics/ directory at {metrics_dir}; check the "
            f"pipeline_dir points at a valid pipeline output."
        )
    return sorted(p.stem for p in metrics_dir.glob("*.csv"))


def load_manifest_from(pipeline_dir, refresh: bool = False) -> pd.DataFrame:
    """Read ``<pipeline_dir>/manifest.csv`` (cached as parquet)."""
    cache = _dir_cache(pipeline_dir, "manifest")
    if cache.exists() and not refresh:
        return pd.read_parquet(cache)
    df = pd.read_csv(Path(pipeline_dir) / "manifest.csv")
    cache.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(cache)
    except Exception:  # noqa: BLE001 — caching is best-effort
        pass
    return df


def load_drawings_from(pipeline_dir, refresh: bool = False) -> pd.DataFrame:
    """Long-form drawings frame for an arbitrary pipeline output.

    Layouts are discovered from ``metrics/*.csv``; one row per
    (graph_id, layout) with the metric columns plus the 24 manifest
    properties merged on. Cached at
    ``<pipeline_dir>/.analysis_cache/drawings.parquet``."""
    cache = _dir_cache(pipeline_dir, "drawings")
    if cache.exists() and not refresh:
        return pd.read_parquet(cache)

    manifest = load_manifest_from(pipeline_dir, refresh=refresh)
    metrics_dir = Path(pipeline_dir) / "metrics"
    parts = []
    for csv_path in sorted(metrics_dir.glob("*.csv")):
        layout = csv_path.stem
        df = pd.read_csv(csv_path)
        if df.empty:
            continue
        df["layout"] = layout
        parts.append(df)
    if not parts:
        raise FileNotFoundError(
            f"No metric CSVs found under {metrics_dir}; check that the "
            f"pipeline output is available."
        )
    drawings = pd.concat(parts, ignore_index=True).merge(
        manifest, on="graph_id", how="left"
    )
    cache.parent.mkdir(parents=True, exist_ok=True)
    try:
        drawings.to_parquet(cache)
    except Exception:  # noqa: BLE001
        pass
    return drawings


def load_envelopes_from(pipeline_dir, refresh: bool = False) -> pd.DataFrame:
    """Per-graph envelope table for an arbitrary pipeline output.

    One row per graph_id with ``<metric>_min``, ``<metric>_max``,
    ``<metric>_mean``, ``<metric>_range`` columns plus the 24 manifest
    properties merged on. Cached at
    ``<pipeline_dir>/.analysis_cache/envelopes.parquet``."""
    cache = _dir_cache(pipeline_dir, "envelopes")
    if cache.exists() and not refresh:
        return pd.read_parquet(cache)

    drawings = load_drawings_from(pipeline_dir, refresh=refresh)
    agg = drawings.groupby("graph_id")[METRICS].agg(["min", "max", "mean"])
    agg.columns = [f"{m}_{stat}" for m, stat in agg.columns]
    for m in METRICS:
        agg[f"{m}_range"] = agg[f"{m}_max"] - agg[f"{m}_min"]
    agg["n_drawings"] = drawings.groupby("graph_id").size()
    agg = agg.reset_index()

    manifest = load_manifest_from(pipeline_dir, refresh=refresh)
    envelopes = agg.merge(manifest, on="graph_id", how="left")
    cache.parent.mkdir(parents=True, exist_ok=True)
    try:
        envelopes.to_parquet(cache)
    except Exception:  # noqa: BLE001
        pass
    return envelopes


def load_corpus(pipeline_dir, refresh: bool = False):
    """Convenience wrapper: returns ``(manifest, drawings, envelopes)``
    for a pipeline directory in one call."""
    manifest = load_manifest_from(pipeline_dir, refresh=refresh)
    drawings = load_drawings_from(pipeline_dir, refresh=refresh)
    envelopes = load_envelopes_from(pipeline_dir, refresh=refresh)
    return manifest, drawings, envelopes


__all__ = [
    "PIPELINE_DIR",
    "MANIFEST_CSV",
    "METRICS_DIR",
    "TIMINGS_DIR",
    "CACHE_DIR",
    "LAYOUTS",
    "ALGORITHMIC_LAYOUTS",
    "CURATOR_LAYOUTS",
    "METRICS",
    "STRUCTURAL_PROPERTIES",
    "COHORTS",
    "load_manifest",
    "load_drawings",
    "load_envelopes",
    "load_metric_timings",
    "load_property_timings",
    "quality_score",
    "cohort_palette",
    # Directory-aware API
    "discover_layouts",
    "load_manifest_from",
    "load_drawings_from",
    "load_envelopes_from",
    "load_corpus",
]
