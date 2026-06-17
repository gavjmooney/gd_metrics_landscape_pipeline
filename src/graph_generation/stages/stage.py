"""Stage stage — parse upstream → filter → write graphmls + manifest rows.

Per-source workers in parallel. Each one parses its upstream archive
or queries an API, canonicalises every graph (undirected, simple, no
self-loops), applies the size + content filters, computes the 24
manifest properties, writes the graphml directly to
``graphs/<category>/<source>/`` (or
``graphs-with-drawings/<source>/``), and returns its accumulated rows.

The parent process drains worker results as they complete and appends
each source's rows to the manifest immediately. Per-source (not
batched-at-end) appends mean an interrupt at source 30/77 leaves every
already-completed source's rows on disk — re-running from scratch is a
no-op for those sources because their graph_ids land in
``existing_ids`` next time around. The ``_timings/properties.csv``
sidecar follows the same per-source append cadence.

Resume contract — ``existing_ids`` (see :func:`_existing_ids`) unions:
  * live ``manifest.csv`` rows,
  * ``manifest.dedup-audit.csv`` (graph_ids dedup previously dropped),
  * ``manifest.sampling-audit.csv`` (graph_ids sample previously
    trimmed from over-cap real_world sources).
Stagers must therefore mint **stable** graph_ids derived from a
durable upstream identifier — never an iteration counter — or the
re-run dedup-audit lookup will miss and the corpus will churn.

There is no separate "promote" stage anymore — content filtering and
property computation that promote used to do live in
:meth:`Stager.stage` itself. See :mod:`graph_generation.stagers.base`
for the per-graph emission pipeline.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, List

import pandas as pd

from .._log import fmt_dur, stopwatch
from ..config import ValidateConfig
from ..manifest import (
    append_property_timings, append_rows,
)
from ..sources import SOURCES, Source
from ..stagers import discover_stagers, stager_for, STAGER_REGISTRY
from .base import PipelineContext, Stage
from . import register_stage


def _resolve_sources(ctx: PipelineContext) -> List[Source]:
    cfg = ctx.config.sources
    selected: List[Source] = []
    by_cat = {"benchmark": cfg.benchmark, "real_world": cfg.real_world,
              "graphs_with_drawings": cfg.graphs_with_drawings}
    for src in SOURCES.values():
        rule = by_cat.get(src.category)
        if rule is None:
            continue
        if rule == "*" or (isinstance(rule, list) and src.name in rule):
            selected.append(src)
    return selected


def _bounds_for(category: str, validate, stage_cfg) -> tuple[int, int]:
    """Resolve (n_min, n_max) for a source's category.

    ``real_world`` and ``benchmark`` use ``stage.n_min_real_world`` (8
    by default — n ≤ 7 is fully covered by exhaustive_small).
    ``graphs_with_drawings`` keeps ``validate.n_min`` so curator-tuned
    drawings on already-known graphs still flow through.
    """
    n_max = validate.n_max
    if category == "graphs_with_drawings":
        return validate.n_min, n_max
    return stage_cfg.n_min_real_world, n_max


def _existing_ids(manifest_path: Path) -> set[str]:
    """Graph_ids the stage stage should treat as already handled.

    Three sources, all unioned:

    1. Live manifest rows — the obvious set of "kept" graphs.
    2. ``manifest.dedup-audit.csv`` — graph_ids the dedup stage
       previously dropped as iso duplicates of a winner. Without
       these, every re-run would re-stage the duplicates, and the
       next dedup pass would drop them again — a per-run write/
       unlink thrash that doesn't change the final corpus.
    3. ``manifest.sampling-audit.csv`` — graph_ids the sample stage
       trimmed from over-cap real_world sources. Same reasoning.

    Mirrors :func:`graph_generation.stages.generate._existing_graph_ids`,
    extended with the sample audit because real_world rows are subject
    to both audits whereas the generate cohorts are only ever subject
    to dedup.
    """
    ids: set[str] = set()
    if manifest_path.exists() and manifest_path.stat().st_size > 0:
        col = pd.read_csv(manifest_path, usecols=["graph_id"])["graph_id"]
        ids.update(str(x) for x in col.dropna())
    for sidecar in ("manifest.dedup-audit.csv",
                    "manifest.sampling-audit.csv"):
        audit_path = manifest_path.with_name(sidecar)
        if audit_path.exists() and audit_path.stat().st_size > 0:
            col = pd.read_csv(audit_path, usecols=["dropped_graph_id"])
            ids.update(str(x) for x in col["dropped_graph_id"].dropna())
    return ids


# --------------------------------------------------------------------------
# Per-source completion sentinels
# --------------------------------------------------------------------------
# ``_existing_ids`` makes resume cheap for any source whose iteration is
# itself cheap (cached archive on disk + per-graph filter). It does NOT
# cover the case where the previous run already finished a source whose
# iteration involves network IO: HoG fetches each of ~29k graph IDs over
# HTTP, NDEx posts a search per query string, Netzschleuder gets a
# catalog per slug. On re-run those iterations re-fire even though every
# graph_id the source can produce is already in the manifest (or in one
# of the audit sidecars, or — in HoG's cap-reached case — implicitly
# excluded because the previous run stopped at max_graphs kept).
#
# The sentinel below records "this source completed under these bounds".
# On a subsequent run we skip the source entirely if the recorded
# (n_min, n_max, max_graphs) match the new run's bounds. Change any of
# those in config and the marker becomes stale, so the source re-runs.
# Delete ``<out>/staging/_completed/<source>.json`` to force a re-stage
# without changing config.

_COMPLETED_DIR = "staging/_completed"


def _sentinel_path(out_dir: Path, source_name: str) -> Path:
    safe = source_name.replace("/", "_")
    return out_dir / _COMPLETED_DIR / f"{safe}.json"


def _completion_key(n_min: int, n_max: int, max_graphs: int) -> str:
    return f"n_min={n_min};n_max={n_max};max_graphs={max_graphs}"


def _is_source_complete(out_dir: Path, source_name: str,
                        n_min: int, n_max: int, max_graphs: int) -> bool:
    path = _sentinel_path(out_dir, source_name)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return data.get("key") == _completion_key(n_min, n_max, max_graphs)


def _mark_source_complete(out_dir: Path, source_name: str,
                          n_min: int, n_max: int, max_graphs: int,
                          kept: int, cap_reached: bool) -> None:
    path = _sentinel_path(out_dir, source_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": source_name,
        "key": _completion_key(n_min, n_max, max_graphs),
        "kept": kept,
        "cap_reached": cap_reached,
        "completed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def _stage_one(source_name: str, out_dir_str: str,
               n_min: int, n_max: int,
               max_graphs: int,
               vc: ValidateConfig,
               existing_ids: set[str]):
    """Worker — runs in a child process.

    Returns a tuple (source_name, kept, reasons, manifest_rows,
    timing_rows, error, elapsed_seconds, cap_reached). The parent merges
    ``manifest_rows`` and ``timing_rows`` once every worker finishes
    and uses ``cap_reached`` only as a diagnostic field in the
    per-source completion sentinel.
    """
    discover_stagers()
    src = SOURCES[source_name]
    t_start = __import__("time").perf_counter()
    try:
        stager = stager_for(src, Path(out_dir_str),
                             n_min=n_min, n_max=n_max,
                             max_graphs=max_graphs,
                             validate_config=vc,
                             existing_ids=existing_ids)
        result = stager.stage()
        return (
            source_name,
            result.kept,
            result.reasons,
            result.manifest_rows,
            result.timing_rows,
            "",
            result.elapsed,
            result.cap_reached,
        )
    except Exception as e:  # noqa: BLE001 — surface to parent
        elapsed = __import__("time").perf_counter() - t_start
        return (source_name, 0, {}, [], [],
                f"{type(e).__name__}: {e}", elapsed, False)


@register_stage
class StageStage(Stage):
    name = "stage"
    parallel = True
    idempotent = True

    def run(self, ctx: PipelineContext) -> None:
        discover_stagers()
        sources = _resolve_sources(ctx)
        if not sources:
            print("[stage] no sources selected; nothing to do")
            return

        unsupported = [s.name for s in sources
                       if s.name not in STAGER_REGISTRY
                       and not any(s.name.startswith(k)
                                   for k in STAGER_REGISTRY if k.endswith("/"))]
        if unsupported:
            print(f"[stage] WARN: {len(unsupported)} sources have no stager: "
                  f"{unsupported[:6]}{'...' if len(unsupported) > 6 else ''}")
            sources = [s for s in sources if s.name not in unsupported]

        workers = max(1, ctx.config.parallel_workers)
        validate = ctx.config.validate
        stage_cfg = ctx.config.stage
        existing_ids = _existing_ids(ctx.manifest_path)

        def _bounds_cap(s: Source) -> tuple[int, int, int]:
            n_min, n_max = _bounds_for(s.category, validate, stage_cfg)
            cap = stage_cfg.caps.get(s.name, stage_cfg.default_cap)
            return n_min, n_max, cap

        # Partition into already-complete (skip entirely) vs to-run.
        completed: List[Source] = []
        to_run: List[Source] = []
        for s in sources:
            n_min, n_max, cap = _bounds_cap(s)
            if _is_source_complete(ctx.out_dir, s.name, n_min, n_max, cap):
                completed.append(s)
            else:
                to_run.append(s)

        print(f"[stage] running {len(to_run)} stagers across "
              f"{workers} workers", flush=True)
        if completed:
            print(f"[stage] {len(completed)} sources already complete "
                  f"(sentinel under {_COMPLETED_DIR}/) — skipping",
                  flush=True)
        if existing_ids:
            print(f"[stage] {len(existing_ids):,} graph_ids already in "
                  f"manifest — will skip", flush=True)

        def _args_for(s: Source):
            n_min, n_max, cap = _bounds_cap(s)
            return (s.name, str(ctx.out_dir), n_min, n_max, cap,
                    validate, existing_ids)

        n_done = 0
        total = len(to_run)
        n_appended = 0
        n_timings_appended = 0

        def _report(result: tuple) -> None:
            nonlocal n_done, n_appended, n_timings_appended
            n_done += 1
            (source_name, kept, reasons, m_rows, t_rows,
             err, dt, cap_reached) = result
            tag = f"{n_done:3d}/{total:3d}"
            if err:
                print(f"[stage] {tag}  FAIL  {source_name}: {err}  "
                      f"({fmt_dur(dt)})", flush=True)
                return
            top_reasons = sorted(reasons.items(), key=lambda kv: -kv[1])[:3]
            reasons_str = "  ".join(f"{k}={v}" for k, v in top_reasons)
            print(f"[stage] {tag}  {source_name:30s} kept={kept:6d}  "
                  f"{reasons_str:50s}  ({fmt_dur(dt)})", flush=True)
            # Per-source append (not batched-at-end) so an interrupt
            # mid-run leaves every completed source's rows in the
            # manifest. ``append_rows`` is module-locked; this loop
            # runs in the parent process only — workers return rows
            # via the future, they don't touch the manifest.
            if m_rows:
                n_appended += append_rows(ctx.manifest_path, m_rows)
            if t_rows:
                n_timings_appended += append_property_timings(
                    ctx.out_dir, t_rows)
            # Mark the source complete only after its rows + timings
            # have been persisted. If append_rows raises, the sentinel
            # never lands and the next run replays this source.
            src = SOURCES.get(source_name)
            if src is not None:
                n_min, n_max, cap = _bounds_cap(src)
                _mark_source_complete(
                    ctx.out_dir, source_name, n_min, n_max, cap,
                    kept=kept, cap_reached=cap_reached,
                )

        if workers == 1 or len(to_run) == 1:
            for s in to_run:
                _report(_stage_one(*_args_for(s)))
        elif to_run:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_stage_one, *_args_for(s)): s.name
                           for s in to_run}
                for fut in as_completed(futures):
                    _report(fut.result())

        if n_appended:
            print(f"[stage] appended {n_appended:,} manifest rows "
                  f"({n_timings_appended:,} property-timing rows)",
                  flush=True)
