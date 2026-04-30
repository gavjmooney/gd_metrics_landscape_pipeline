"""Metrics stage — compute each registered metric over every drawing.

Walks ``out/drawings/<layout>/<category>/<source>/<graph_id>``,
applies the metric registry, and writes one row per (layout, graph)
pair to ``out/metrics/<layout>.csv``. Resume-safe: graph_ids already
present in the per-layout CSV are skipped.
"""

from __future__ import annotations

import csv
import math
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
from tqdm import tqdm

from ..manifest import resolve_drawing_path
from ..metrics import METRIC_REGISTRY, make_context
from .base import PipelineContext, Stage
from . import register_stage


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


def _compute_one(drawing_path: str, metric_names: List[str]
                  ) -> Tuple[Dict[str, float], str]:
    """Worker — returns (metric_values, error_or_blank)."""
    import geg
    try:
        G = geg.read_drawing(drawing_path)
    except Exception as e:
        return {}, f"load_failed:{type(e).__name__}:{e}"
    ctx = make_context(G)
    out: Dict[str, float] = {}
    for name in metric_names:
        try:
            out[name] = float(METRIC_REGISTRY[name].fn(G, ctx))
        except Exception:
            out[name] = float("nan")
    return out, ""


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
            self._run_one_layout(ctx, layout, metric_names, rows)

    @staticmethod
    def _run_one_layout(ctx: PipelineContext, layout: str,
                        metric_names: List[str], rows: List[Dict]) -> None:
        out_csv = ctx.out_dir / "metrics" / f"{layout}.csv"
        out_csv.parent.mkdir(parents=True, exist_ok=True)

        done = _existing_ids(out_csv)
        is_fresh = not out_csv.exists() or out_csv.stat().st_size == 0
        cf = out_csv.open("a", newline="", encoding="utf-8")
        writer = csv.writer(cf)
        if is_fresh:
            writer.writerow(["graph_id"] + metric_names)

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

        def _emit(gid: str, vals: Dict[str, float]) -> None:
            writer.writerow([gid] + [_fmt(vals.get(n, float("nan")))
                                       for n in metric_names])
            cf.flush()

        try:
            if workers == 1 or len(pending) == 1:
                for gid, path in tqdm(pending, unit="drawing",
                                        desc=f"[metrics] {layout}"):
                    vals, err = _compute_one(path, metric_names)
                    if err:
                        n_failed += 1
                        continue
                    _emit(gid, vals)
                    n_done += 1
            else:
                with ProcessPoolExecutor(max_workers=workers) as pool:
                    futures = {pool.submit(_compute_one, path, metric_names): gid
                               for gid, path in pending}
                    for fut in tqdm(as_completed(futures), total=len(futures),
                                     unit="drawing",
                                     desc=f"[metrics] {layout}"):
                        gid = futures[fut]
                        vals, err = fut.result()
                        if err:
                            n_failed += 1
                            continue
                        _emit(gid, vals)
                        n_done += 1
        finally:
            cf.close()
        print(f"[metrics] {layout}: ok={n_done} failed={n_failed}")
