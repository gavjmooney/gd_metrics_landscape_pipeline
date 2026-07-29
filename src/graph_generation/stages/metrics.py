"""Metrics stage — compute each registered metric over every drawing.

Walks ``out/drawings/<layout>/<category>/<source>/<graph_id>``,
applies the metric registry, and writes one row per (layout, graph)
pair to ``out/metrics/<layout>.csv``. Resume-safe: graph_ids already
present in the per-layout CSV are skipped.

Each row also carries two descriptive geometry flags AFTER the metric
columns — ``contains_bends`` and ``contains_curves`` (see
:data:`GEOMETRY_COLUMNS` / :func:`edge_geometry_flags`). They are derived
straight from the drawing's edge ``path`` strings (not from ``geg`` or the
manifest properties) and record whether the layout actually drew any
polyline bends and/or curved edges. The fused mode in ``stages/layout.py``
emits the identical columns so both producers of ``metrics/<layout>.csv``
stay header-compatible.
"""

from __future__ import annotations

import csv
import math
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
from tqdm import tqdm

from .._log import fmt_dur, stopwatch
from ..manifest import append_metric_timings, resolve_drawing_path
from ..metrics import METRIC_REGISTRY, make_context
from ._cleanup import clean_metric_csv, clean_metric_timings
from .base import PipelineContext, Stage
from . import register_stage


# Descriptive per-drawing geometry flags appended to every metrics CSV
# AFTER the metric columns. They are NOT metrics (not in METRIC_REGISTRY,
# not timed) — they record what kind of edge geometry the drawing actually
# carries, computed directly from the edge `path` strings.
GEOMETRY_COLUMNS: List[str] = ["contains_bends", "contains_curves"]

# Curve commands (cubic/quadratic/smooth/arc), upper- and lower-case. The
# exponent letter `e`/`E` of scientific-notation coordinates is deliberately
# NOT in this set, so it can never be miscounted as a command (the bug in
# geg.contains_curves). No SVG numeric literal contains C/Q/S/T/A either.
_CURVE_CMD_RE = re.compile(r"[CQSTAcqsta]")
# Straight-line commands (line-to / horizontal / vertical), both cases.
_LINE_CMD_RE = re.compile(r"[LHVlhv]")


def edge_geometry_flags(G) -> Dict[str, bool]:
    """Per-drawing geometry flags derived ONLY from edge ``path`` strings.

    Deliberately independent of ``geg`` and the manifest graph_properties
    (per spec): we scan the raw SVG ``path`` of every edge.

    - ``contains_curves``: any edge path has a curve command
      (``C``/``Q``/``S``/``T``/``A``, case-insensitive).
    - ``contains_bends``: any edge path is a straight-line polyline with an
      interior vertex — i.e. it has >= 2 line commands (``L``/``H``/``V``).
      A plain straight edge is exactly one ``M`` + one ``L`` (one line
      command) and is NOT a bend.

    The two are independent — a drawing may have both (e.g. a path with two
    ``L`` segments and a ``C``), one, or neither. An edge with no ``path`` is
    a straight node-to-node chord and contributes neither.
    """
    contains_curves = False
    contains_bends = False
    for _, _, d in G.edges(data=True):
        path = d.get("path")
        if not path:
            continue
        if not contains_curves and _CURVE_CMD_RE.search(path):
            contains_curves = True
        if not contains_bends and len(_LINE_CMD_RE.findall(path)) >= 2:
            contains_bends = True
        if contains_curves and contains_bends:
            break
    return {"contains_bends": contains_bends, "contains_curves": contains_curves}


def _selected_metrics(ctx: PipelineContext) -> List[str]:
    cfg = ctx.config.metrics.selected
    if cfg == "*":
        return sorted(METRIC_REGISTRY)
    return [n for n in cfg if n in METRIC_REGISTRY]


def _selected_layouts(ctx: PipelineContext) -> List[str]:
    from ..layouts import LAYOUT_REGISTRY
    cfg = ctx.config.layouts
    if cfg.selected == "*":
        names = list(LAYOUT_REGISTRY)
    else:
        names = [n for n in cfg.selected if n in LAYOUT_REGISTRY]
    return [n for n in names if n not in cfg.exclude]


def _fmt(v) -> str:
    if isinstance(v, float):
        if math.isnan(v):
            return "nan"
        return f"{v:.9g}"
    return str(v)


def _existing_ids(csv_path: Path) -> set[str]:
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return set()
    with csv_path.open(newline="", encoding="utf-8") as f:
        return {row["graph_id"] for row in csv.DictReader(f)}


def compute_in_memory(G, metric_names: List[str]
                       ) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Compute every selected metric on an in-memory drawing graph.

    Returns ``(values, per_metric_seconds)``. The graph must already
    carry x/y on nodes and (optionally) bends on edges — i.e. the
    output of a layout function after standardisation. Used both by
    the standalone metrics stage (after re-reading a drawing) and by
    the fused mode of the layout stage (compute right after the
    layout while the graph is still in memory).
    """
    import time as _time
    ctx = make_context(G)
    out: Dict[str, float] = {}
    timings: Dict[str, float] = {}
    for name in metric_names:
        t0 = _time.perf_counter()
        try:
            out[name] = float(METRIC_REGISTRY[name].fn(G, ctx))
        except Exception:
            out[name] = float("nan")
        timings[name] = _time.perf_counter() - t0
    # Append the descriptive geometry flags (GEOMETRY_COLUMNS). Not metrics,
    # so they ride in the values dict but never the timings dict. Guarded so
    # a malformed path can't sink the whole row.
    try:
        out.update(edge_geometry_flags(G))
    except Exception:
        for col in GEOMETRY_COLUMNS:
            out.setdefault(col, False)
    return out, timings


def _compute_one(drawing_path: str, metric_names: List[str]
                  ) -> Tuple[Dict[str, float], Dict[str, float], str]:
    """Worker — returns (metric_values, per_metric_seconds, error_or_blank)."""
    import geg
    try:
        G = geg.read_drawing(drawing_path)
    except Exception as e:
        return {}, {}, f"load_failed:{type(e).__name__}:{e}"
    out, timings = compute_in_memory(G, metric_names)
    return out, timings, ""


@register_stage
class MetricsStage(Stage):
    name = "metrics"
    parallel = True
    idempotent = True

    def run(self, ctx: PipelineContext) -> None:
        manifest_path = ctx.manifest_path
        if not manifest_path.exists():
            print("[metrics] no manifest")
            return

        metric_names = _selected_metrics(ctx)
        layouts = _selected_layouts(ctx)
        if not metric_names:
            print("[metrics] no metrics selected")
            return
        if not layouts:
            print("[metrics] no layouts selected")
            return

        manifest = pd.read_csv(manifest_path, low_memory=False)
        rows = manifest.to_dict(orient="records")

        for layout in layouts:
            with stopwatch() as elapsed:
                self._run_one_layout(ctx, layout, metric_names, rows)
            print(f"[metrics] {layout}: total {fmt_dur(elapsed())}",
                  flush=True)

    @staticmethod
    def _run_one_layout(ctx: PipelineContext, layout: str,
                        metric_names: List[str], rows: List[Dict]) -> None:
        out_csv = ctx.out_dir / "metrics" / f"{layout}.csv"
        out_csv.parent.mkdir(parents=True, exist_ok=True)

        # Resume hygiene: drop orphan rows (graph_id no longer in
        # manifest) and collapse duplicate rows that earlier interrupts
        # may have left behind. The returned set is the in-memory cache
        # key — re-reading the file later would race with this run's
        # appends and re-skip rows we just wrote.
        valid_ids = {str(r["graph_id"]) for r in rows}
        done = clean_metric_csv(out_csv, valid_ids)
        clean_metric_timings(ctx.out_dir / "_timings" / "metrics.csv",
                              layout, valid_ids)
        is_fresh = not out_csv.exists() or out_csv.stat().st_size == 0
        cf = out_csv.open("a", newline="", encoding="utf-8")
        writer = csv.writer(cf)
        out_columns = metric_names + GEOMETRY_COLUMNS
        if is_fresh:
            writer.writerow(["graph_id"] + out_columns)

        pending: List[Tuple[str, str]] = []
        for r in rows:
            gid = r["graph_id"]
            if gid in done:
                continue
            r2 = dict(r)
            if not isinstance(r2.get("source"), str):
                r2["source"] = ""
            path = resolve_drawing_path(ctx.out_dir, layout, r2)
            if path.exists():
                pending.append((gid, str(path)))

        if not pending:
            print(f"[metrics] {layout}: nothing to do")
            cf.close()
            return

        n_done = n_failed = 0
        workers = max(1, ctx.config.parallel_workers)
        timing_buffer: List[Dict] = []

        def _emit(gid: str, vals: Dict[str, float],
                  metric_timings: Dict[str, float]) -> None:
            writer.writerow([gid] + [_fmt(vals.get(n, float("nan")))
                                       for n in out_columns])
            cf.flush()
            timing_buffer.append({"graph_id": gid, "timings": metric_timings})
            # Flush the timings buffer in batches so partial runs leave
            # a usable sidecar (and so we don't carry millions of rows
            # in memory before metrics finishes).
            if len(timing_buffer) >= 1000:
                append_metric_timings(ctx.out_dir, layout, timing_buffer)
                timing_buffer.clear()

        try:
            if workers == 1 or len(pending) == 1:
                for gid, path in tqdm(pending, unit="drawing",
                                        desc=f"[metrics] {layout}"):
                    vals, mt, err = _compute_one(path, metric_names)
                    if err:
                        n_failed += 1
                        continue
                    _emit(gid, vals, mt)
                    n_done += 1
            else:
                with ProcessPoolExecutor(max_workers=workers) as pool:
                    futures = {pool.submit(_compute_one, path, metric_names): gid
                               for gid, path in pending}
                    for fut in tqdm(as_completed(futures), total=len(futures),
                                     unit="drawing",
                                     desc=f"[metrics] {layout}"):
                        gid = futures[fut]
                        vals, mt, err = fut.result()
                        if err:
                            n_failed += 1
                            continue
                        _emit(gid, vals, mt)
                        n_done += 1
        finally:
            cf.close()
            if timing_buffer:
                append_metric_timings(ctx.out_dir, layout, timing_buffer)
        print(f"[metrics] {layout}: ok={n_done} failed={n_failed}")
