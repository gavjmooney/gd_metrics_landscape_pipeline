"""Manifest schema, atomic append, and graph-path helpers.

The corpus output root is supplied by :class:`PipelineContext`
(populated from ``[pipeline].out_dir`` in the config). This module
no longer reads ``GRAPH_GEN_OUT`` directly — config is the source of
truth.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import threading
from pathlib import Path
from typing import Any, Dict, IO, Iterable, Optional

import networkx as nx

from .properties import MANIFEST_PROPERTY_ORDER


_MANIFEST_LOCK = threading.Lock()


MANIFEST_HEADER = [
    "graph_id", "generator", "category", "source", "seed", "params_json",
    *MANIFEST_PROPERTY_ORDER,
    "generated_at_utc",
]

# Subdirs under output/graphs/ and output/drawings/<algo>/.
# ``benchmark``, ``real_world``, and ``graphs_with_drawings`` have an
# additional ``<source>/`` level (rome, north, pajek, wikipathways,
# ...); ``generated`` and ``calibration`` are flat under their category.
#
# ``graphs_with_drawings`` is special in one more way — it lives at
# ``output/graphs-with-drawings/`` (hyphens, top-level, parallel to
# ``graphs/``), not under ``graphs/``. The graphml files there carry
# the curator's original x/y (+ width/height/colour/shape) as node
# attributes, so layout-preservation is part of the cohort contract.
CATEGORIES = ("generated", "calibration", "benchmark", "real_world",
              "graphs_with_drawings")
NESTED_CATEGORIES = ("benchmark", "real_world", "graphs_with_drawings")


def graph_filename(generator: str, n: int, m: int, seed: int) -> str:
    return f"{generator}_n{n:03d}_m{m:04d}_s{seed}.graphml"


def write_graph(G: nx.Graph, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # networkx graphml writer requires string keys; we use int node labels
    # which it handles fine via its default serialiser
    nx.write_graphml(G, path)


class ManifestWriter:
    """Append-only CSV writer. Opens on __enter__, flushes after every row
    so a crashed run leaves a usable partial manifest."""

    def __init__(self, path: Path):
        self.path = path
        self._file: Optional[IO[str]] = None
        self._writer: Optional[csv.DictWriter] = None

    def __enter__(self) -> "ManifestWriter":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not self.path.exists() or self.path.stat().st_size == 0
        self._file = self.path.open("a", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=MANIFEST_HEADER,
                                      extrasaction="ignore")
        if is_new:
            self._writer.writeheader()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
            self._writer = None

    def append(
        self,
        *,
        graph_id: str,
        generator: str,
        category: str,
        seed: int,
        params: Dict[str, Any],
        properties: Dict[str, Any],
        source: str = "",
    ) -> None:
        assert self._writer is not None, "use as a context manager"
        if category not in CATEGORIES:
            raise ValueError(f"category must be one of {CATEGORIES}, got {category!r}")
        if category in NESTED_CATEGORIES and not source:
            raise ValueError(
                f"category {category!r} requires a non-empty 'source' (e.g. 'rome', 'north')"
            )
        if category not in NESTED_CATEGORIES and source:
            raise ValueError(
                f"'source' must be empty for category {category!r} (got {source!r})"
            )
        row: Dict[str, Any] = {
            "graph_id": graph_id,
            "generator": generator,
            "category": category,
            "source": source,
            "seed": seed,
            "params_json": json.dumps(params, separators=(",", ":"), sort_keys=True),
            **properties,
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        }
        with _MANIFEST_LOCK:
            self._writer.writerow(row)
            self._file.flush()


def append_property_timings(out_dir: Path,
                             rows: Iterable[Dict[str, Any]]) -> int:
    """Append per-property timing rows to ``<out>/_timings/properties.csv``.

    Each input row must have ``graph_id``, ``n_nodes``, ``n_edges``,
    and ``timings`` (a ``{prop_name: seconds}`` dict). One CSV row is
    written per (graph, property) pair so the file can be plotted
    seconds-vs-n grouped by property to inspect empirical complexity.
    """
    target = out_dir / "_timings" / "properties.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    is_new = not target.exists() or target.stat().st_size == 0
    written = 0
    with target.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "graph_id", "n_nodes", "n_edges", "property", "seconds"])
        if is_new:
            writer.writeheader()
        for r in rows:
            gid = r["graph_id"]
            n = r.get("n_nodes")
            m = r.get("n_edges")
            for prop, secs in (r.get("timings") or {}).items():
                writer.writerow({
                    "graph_id": gid, "n_nodes": n, "n_edges": m,
                    "property": prop, "seconds": f"{secs:.6f}",
                })
                written += 1
        f.flush()
    return written


def append_metric_timings(out_dir: Path, layout: str,
                           rows: Iterable[Dict[str, Any]]) -> int:
    """Append per-metric timing rows to ``<out>/_timings/metrics.csv``.

    One CSV row per (graph_id, layout, metric). Same shape as
    :func:`append_property_timings` but with a ``layout`` column so a
    single file can be sliced per algorithm.
    """
    target = out_dir / "_timings" / "metrics.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    is_new = not target.exists() or target.stat().st_size == 0
    written = 0
    with target.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "graph_id", "layout", "metric", "seconds"])
        if is_new:
            writer.writeheader()
        for r in rows:
            gid = r["graph_id"]
            for metric, secs in (r.get("timings") or {}).items():
                writer.writerow({
                    "graph_id": gid, "layout": layout,
                    "metric": metric, "seconds": f"{secs:.6f}",
                })
                written += 1
        f.flush()
    return written


def append_rows(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    """Append a batch of pre-built rows. Acquires the module-level lock
    for the whole batch so concurrent writers from different stages stay
    atomic. Returns the number of rows written.

    Each row must already include the manifest schema columns; missing
    optional columns default to empty strings. Use this from per-source
    promotion code that has already computed properties for each row.
    """
    written = 0
    with _MANIFEST_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not path.exists() or path.stat().st_size == 0
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=MANIFEST_HEADER,
                                    extrasaction="ignore")
            if is_new:
                writer.writeheader()
            now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            for row in rows:
                row.setdefault("generated_at_utc", now)
                row.setdefault("source", "")
                writer.writerow(row)
                written += 1
            f.flush()
    return written


def graphs_dir(out: Path, category: str, source: str = "") -> Path:
    """Directory that holds graphml files for a category (and an
    optional source, for ``benchmark``/``real_world``/
    ``graphs_with_drawings``).

    ``graphs_with_drawings`` lives at the hyphenated top-level path
    ``graphs-with-drawings/<source>/`` (not under ``graphs/``) so it's
    visibly distinct from topology-only cohorts.
    """
    if category not in CATEGORIES:
        raise ValueError(f"category must be one of {CATEGORIES}, got {category!r}")
    if category == "graphs_with_drawings":
        if not source:
            raise ValueError("graphs_with_drawings requires a source subfolder")
        return out / "graphs-with-drawings" / source
    base = out / "graphs" / category
    if category in NESTED_CATEGORIES:
        if not source:
            raise ValueError(f"category {category!r} requires a source subfolder")
        return base / source
    if source:
        raise ValueError(f"category {category!r} does not use a source subfolder")
    return base


def resolve_graph_path(out: Path, row: Dict[str, Any]) -> Path:
    """Path to the topology graphml for a manifest row."""
    return graphs_dir(out, row["category"], row.get("source") or "") / row["graph_id"]


def resolve_drawing_path(out: Path, algo: str, row: Dict[str, Any]) -> Path:
    """Path to the positioned drawing graphml for a manifest row under a
    given layout algorithm."""
    cat = row["category"]
    if cat not in CATEGORIES:
        raise ValueError(f"category must be one of {CATEGORIES}, got {cat!r}")
    base = out / "drawings" / algo / cat
    if cat in NESTED_CATEGORIES:
        src = row.get("source") or ""
        if not src:
            raise ValueError(f"row requires a source for category {cat!r}")
        return base / src / row["graph_id"]
    return base / row["graph_id"]
