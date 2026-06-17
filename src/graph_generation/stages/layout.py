"""Layout stage - run every selected layout over every manifest row."""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import networkx as nx
import numpy as np
import pandas as pd
from tqdm import tqdm

from .. import seeds
from .._log import fmt_dur, stopwatch
from ..layouts import LAYOUT_REGISTRY, Layout, NotApplicable
from ..layouts._native import canonicalise_node_order
from ..layouts._timeout import LayoutTimeout, call_with_timeout, prewarm
from ..manifest import resolve_drawing_path, resolve_graph_path
from ..rescale import DIAMETER, standardise
from .base import PipelineContext, Stage
from . import register_stage


def _verify_ids(rows: List[Dict], n: int) -> set:
    """Pick a deterministic per-source sample of graph_ids for visual
    verification. Used in fused mode (``write_drawings=False``) to
    keep ``n`` drawings per source on disk so the layouts can still
    be eyeballed after the run.

    Grouping:
      - ``benchmark`` / ``real_world`` / ``graphs_with_drawings``:
        by ``source`` (the cohort's per-dataset key).
      - ``generated`` / ``calibration``: by ``generator`` (sampled
        family or "exhaustive_small" / "calibration") because the
        ``source`` field is empty for these cohorts.

    Picks the lexicographically-smallest graph_ids per group so the
    sample is stable across reruns and config changes.
    """
    if n <= 0:
        return set()
    by_group: Dict[Tuple[str, str], List[str]] = {}
    for r in rows:
        cat = r.get("category", "")
        key_extra = r.get("source") or r.get("generator") or ""
        by_group.setdefault((cat, key_extra), []).append(r["graph_id"])
    out: set = set()
    for ids in by_group.values():
        ids.sort()
        out.update(ids[:n])
    return out


def _read_latest_progress(log_path: Path) -> str:
    """Extract the most recent tqdm-style progress line from a
    subprocess log file. Used by the parallel-layout dashboard.

    tqdm overwrites a single line via ``\\r``; redirected to a file
    those overwrites accumulate into one big buffer. We seek to the
    last ~16 KB, split on \\r and \\n, and take the most recent
    non-empty chunk that looks like a progress line.
    """
    try:
        with log_path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 16384))
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    tail = tail.replace("\r", "\n")
    for line in reversed(tail.splitlines()):
        line = line.strip()
        if line and ("%|" in line or "graph/s" in line
                       or "drawing/s" in line or "graph/it" in line):
            return line
    return ""


def _replace_with_retry(src, dst, attempts: int = 5,
                        delay_s: float = 0.05) -> None:
    """``src.replace(dst)`` with a brief retry on ``FileNotFoundError``.

    drvfs (the WSL ↔ NTFS filesystem) occasionally returns ENOENT on a
    fresh ``.tmp`` file at rename time when many workers are writing
    into the same directory. The file IS there — by the next syscall
    the metadata catches up. A handful of retries with a 50ms backoff
    eliminates the race without giving up atomicity.
    """
    for i in range(attempts):
        try:
            src.replace(dst)
            return
        except FileNotFoundError:
            if i == attempts - 1:
                raise
            time.sleep(delay_s * (i + 1))


def _select_layouts(selected, exclude: List[str]) -> List[Layout]:
    if isinstance(selected, str) and selected == "*":
        names = sorted(LAYOUT_REGISTRY)
    elif isinstance(selected, (list, tuple)):
        names = list(selected)
    else:
        names = [str(selected)]
    excluded = set(exclude or [])
    out: List[Layout] = []
    for name in names:
        if name in excluded:
            continue
        if name not in LAYOUT_REGISTRY:
            print(f"[layout] unknown layout {name!r}; skipping", file=sys.stderr)
            continue
        out.append(LAYOUT_REGISTRY[name])
    return out


_OUTCOME_OK = "ok"
_OUTCOME_SKIPPED_CACHED = "cached"
_OUTCOME_SKIPPED_NA = "not_applicable"
_OUTCOME_TIMEOUT = "timeout"
_OUTCOME_FAILED = "failed"


def _per_graph_seed(layout_ss: np.random.SeedSequence,
                    graph_id: str) -> int:
    """Deterministic per-graph seed for a (layout, graph) pair.

    Pure function of (layout_ss, graph_id): adding/removing/reordering
    other graphs in the manifest does not change this graph's seed.
    See :func:`graph_generation.seeds.keyed` for the byte-derivation
    scheme.
    """
    return seeds.keyed_int(layout_ss, graph_id)


def _run_one(layout_name: str, graph_path: str, drawing_path: str,
             seed: int, row: Dict,
             write_drawings: bool = True,
             metric_names: Optional[List[str]] = None,
             cached_metric_ids: Optional[set] = None,
             verify_ids: Optional[set] = None,
             ) -> Tuple[str, str, Optional[str], float,
                        Dict[str, float], Dict[str, float]]:
    """Worker — load graph, run layout, optionally write + compute metrics.

    Modes:
      - ``write_drawings=True`` (default): persist the drawing graphml
        to ``drawing_path``; metric_names typically empty.
      - ``write_drawings=False``: skip the graphml write and instead
        compute metrics in-memory on the freshly-laid-out graph,
        returning metric values + per-metric timings. Halves the IO
        on slow filesystems.
      - ``verify_ids``: graph_ids in this set always have their
        drawing written, even in fused mode — gives a deterministic
        per-source sample for visual inspection.

    Returns ``(graph_id, outcome, error_or_none, seconds,
    metric_values, metric_timings)``. The two metric dicts are empty
    when ``write_drawings=True``.
    """
    graph_id = row["graph_id"]
    layout = LAYOUT_REGISTRY[layout_name]
    out_path = Path(drawing_path)

    # In fused mode, verify_ids carry an additional drawing-write
    # responsibility on top of the in-memory metrics computation.
    is_verify = bool(verify_ids and graph_id in verify_ids)
    do_write = write_drawings or is_verify

    # Idempotency: a cached drawing OR a metric row already on disk
    # for this (graph, layout) is enough to skip. In fused mode we
    # gate on the metric row (the canonical cache key); a missing
    # verify drawing on disk still triggers a re-run so the sample
    # gets written.
    if write_drawings:
        if out_path.exists():
            return graph_id, _OUTCOME_SKIPPED_CACHED, None, 0.0, {}, {}
    else:
        if cached_metric_ids and graph_id in cached_metric_ids:
            # Verify-drawing on disk too? If so, fully cached.
            if not is_verify or out_path.exists():
                return graph_id, _OUTCOME_SKIPPED_CACHED, None, 0.0, {}, {}

    src = Path(graph_path)
    if not src.exists():
        return (graph_id, _OUTCOME_FAILED,
                f"missing source graph: {src}", 0.0, {}, {})

    try:
        G = nx.read_graphml(src)
    except Exception as e:
        return graph_id, _OUTCOME_FAILED, f"read_graphml: {e}", 0.0, {}, {}

    # Force a canonical node iteration order before handing G to any
    # layout. networkx walks nodes in insertion order, which equals the
    # order they were written to graphml — so a graphml with shuffled
    # node order would yield a different "deterministic" layout. This
    # rebuild restores order-independence for every backend (native,
    # OGDF, Graphviz). Node identities are unchanged, only iteration.
    G = canonicalise_node_order(G)

    try:
        if not layout.applies_to(G):
            return graph_id, _OUTCOME_SKIPPED_NA, None, 0.0, {}, {}
    except Exception as e:
        return graph_id, _OUTCOME_FAILED, f"applies_to: {e}", 0.0, {}, {}

    t0 = time.perf_counter()
    try:
        if layout.timeout_s is not None:
            positions, bends = call_with_timeout(
                layout.fn, G, seed, layout.timeout_s)
        else:
            positions, bends = layout.fn(G, seed)
    except NotApplicable:
        return graph_id, _OUTCOME_SKIPPED_NA, None, 0.0, {}, {}
    except LayoutTimeout as e:
        dt = time.perf_counter() - t0
        return graph_id, _OUTCOME_TIMEOUT, str(e), dt, {}, {}
    except Exception as e:
        return (graph_id, _OUTCOME_FAILED,
                f"{type(e).__name__}: {e}", 0.0, {}, {})
    dt = time.perf_counter() - t0

    metric_values: Dict[str, float] = {}
    metric_timings: Dict[str, float] = {}
    try:
        positions, bends = standardise(positions, bends or {})
        for nid, xy in positions.items():
            if nid not in G.nodes:
                return (graph_id, _OUTCOME_FAILED,
                        f"unknown node {nid!r}", dt, {}, {})
            G.nodes[nid]["x"] = float(xy[0])
            G.nodes[nid]["y"] = float(xy[1])
            G.nodes[nid]["width"] = DIAMETER
            G.nodes[nid]["height"] = DIAMETER
        if bends:
            for (u, v), pts in bends.items():
                if not G.has_edge(u, v):
                    continue
                G.edges[u, v]["bends"] = list(pts)
                # ``geg.to_svg`` and the bezier crossing metrics read
                # the SVG-style ``path`` attr, not ``bends``. Without
                # this synthesis HOLA's orthogonal routing renders as
                # straight lines in the verify-sample SVGs and the
                # bezier metric falls back to straight-edge geometry.
                u_xy = (G.nodes[u]["x"], G.nodes[u]["y"])
                v_xy = (G.nodes[v]["x"], G.nodes[v]["y"])
                pts_full = [u_xy, *pts, v_xy]
                G.edges[u, v]["path"] = "M" + " L".join(
                    f"{x},{y}" for x, y in pts_full)
                # geg's curves_promotion only expands an edge into its
                # constituent waypoints when ``polyline=True``; without
                # the flag the SVG bbox is computed from node positions
                # only and any bend that routes outside the node hull
                # gets clipped at the viewBox edge (sugiyama / arc-bfs /
                # HOLA / orthogonal layouts visibly cut off otherwise).
                G.edges[u, v]["polyline"] = True

        if do_write:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            # Per-process .tmp suffix so 8 workers writing into the same
            # directory never share a name. drvfs (WSL ↔ NTFS) drops
            # freshly-written file metadata under contention; per-pid
            # naming + a brief retry side-steps the race.
            suffix = f".{os.getpid()}.tmp"
            tmp = out_path.with_suffix(out_path.suffix + suffix)
            try:
                import geg as _geg
                _geg.write_graphml(G, str(tmp))
            except ImportError:
                _geg = None
                nx.write_graphml(G, tmp)
            _replace_with_retry(tmp, out_path)
            # Also emit an SVG render alongside so the visual sample
            # is browseable without re-rendering. Best effort — if
            # SVG fails (e.g. a degenerate graph), the graphml stays.
            if _geg is not None:
                svg_path = out_path.with_suffix(".svg")
                try:
                    _geg.to_svg(G, str(svg_path))
                except Exception:
                    if svg_path.exists():
                        try:
                            svg_path.unlink()
                        except OSError:
                            pass

        if metric_names:
            from .metrics import compute_in_memory
            metric_values, metric_timings = compute_in_memory(G, metric_names)
    except Exception as e:
        return graph_id, _OUTCOME_FAILED, f"write: {e}", dt, {}, {}

    return graph_id, _OUTCOME_OK, None, dt, metric_values, metric_timings


@register_stage
class LayoutStage(Stage):
    name = "layout"
    parallel = True
    idempotent = True

    def run(self, ctx: PipelineContext) -> None:
        if not ctx.manifest_path.exists():
            print("[layout] no manifest; nothing to lay out")
            return

        layouts = _select_layouts(ctx.config.layouts.selected,
                                   ctx.config.layouts.exclude)
        if not layouts:
            print("[layout] no layouts selected")
            return

        df = pd.read_csv(ctx.manifest_path, low_memory=False)
        if df.empty:
            print("[layout] manifest is empty")
            return

        df["source"] = df["source"].fillna("").astype(str)
        rows = df.to_dict("records")
        n_parallel = max(1, int(ctx.config.layouts.parallel_layouts or 1))
        n_parallel = min(n_parallel, len(layouts))
        print(f"[layout] graphs={len(rows):,}  layouts={len(layouts)}  "
              f"workers={ctx.config.parallel_workers}  "
              f"parallel_layouts={n_parallel}")

        if n_parallel > 1:
            self._run_parallel(ctx, layouts)
        else:
            layout_stage_ss = seeds.stage(ctx.root_ss, seeds.StageSeed.LAYOUT)

            summary: Dict[str, Dict[str, int]] = {}
            timings: Dict[str, float] = {}
            for layout in layouts:
                # Per-layout seed is keyed by layout name — adding a new
                # layout to the registry never perturbs an existing one.
                l_ss = seeds.keyed(layout_stage_ss, layout.name)
                with stopwatch() as elapsed:
                    summary[layout.name] = self._run_layout(
                        ctx, layout, l_ss, rows,
                    )
                timings[layout.name] = elapsed()
                print(f"[layout] {layout.name:<22s} done in "
                      f"{fmt_dur(elapsed())}", flush=True)

            print()
            print("[layout] summary")
            print(f"  {'layout':<22s} {'ok':>6s} {'cached':>7s} "
                  f"{'n/a':>5s} {'timeout':>7s} {'fail':>5s}  "
                  f"{'elapsed':>9s}")
            for name, s in summary.items():
                print(f"  {name:<22s} {s['ok']:>6d} {s['cached']:>7d} "
                      f"{s['na']:>5d} {s['timeout']:>7d} "
                      f"{s['fail']:>5d}  "
                      f"{fmt_dur(timings[name]):>9s}")

        # Rebuild the verify-drawings HTML viewer at the end of every
        # top-level layout invocation. Single-layout subprocesses
        # spawned by the parallel dispatcher set
        # ``PIPELINE_VIEWER_AUTOBUILD=0`` so only the outer parent
        # does it once — avoiding 12 racing writers on the same file.
        if os.environ.get("PIPELINE_VIEWER_AUTOBUILD", "1") != "0":
            try:
                from .. import viewer
                n_svgs, path = viewer.build(ctx.out_dir)
                if n_svgs:
                    print(f"[layout] viewer → {path.name} "
                          f"({n_svgs:,} drawings)", flush=True)
            except Exception as e:
                # Viewer build failure should never sink the run.
                print(f"[layout] viewer build skipped: "
                      f"{type(e).__name__}: {e}", file=sys.stderr,
                      flush=True)

    @staticmethod
    def _run_parallel(ctx: PipelineContext,
                       layouts: List[Layout]) -> None:
        """Spawn one Python subprocess per layout, ``parallel_layouts``
        of them at a time. Each subprocess invokes the same ``pipeline
        run layout --layouts <one>`` so it goes through the canonical
        serial inner loop with no fork-with-networkx-loaded penalty.

        Per-layout logs land at ``<out>/log.06-layout.<name>.txt``;
        the parent prints ``[layout] N/M  <name>  ok / done in …`` as
        each subprocess exits, and a daemon dashboard thread prints a
        periodic block summarising every still-running layout's tqdm
        progress so live status is visible without tailing N files.

        Completion lines are also appended directly to
        ``<out>/log.06-layout.summary.txt`` — a sidecar that bypasses
        whatever ``tee`` / pipe / buffering the user may have wrapped
        around stdout. We've seen the stdout completion lines go missing
        in long runs (10h+) for reasons we couldn't reliably reproduce;
        the sidecar is the authoritative record of what finished when.
        """
        import subprocess
        import sys as _sys
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        out_dir = ctx.out_dir
        log_dir = out_dir
        cap = max(1, min(int(ctx.config.layouts.parallel_layouts),
                         len(layouts)))
        config_path = ctx.config.source_path
        n = len(layouts)
        n_done = 0

        summary_path = log_dir / "log.06-layout.summary.txt"
        summary_lock = threading.Lock()
        summary_log = summary_path.open("a", encoding="utf-8")

        def _summary(line: str) -> None:
            """Append ``line`` to the sidecar summary log AND mirror it
            to stdout. Holding ``summary_lock`` keeps the file write
            atomic with respect to other writers (the dashboard
            doesn't write here, but be safe in case future code does)."""
            with summary_lock:
                summary_log.write(line + "\n")
                summary_log.flush()
            print(line, flush=True)

        # Shared state for the dashboard thread.
        state: Dict[str, Dict] = {
            lyt.name: {"status": "queued", "log_path": None,
                        "started_at": None}
            for lyt in layouts
        }
        state_lock = threading.Lock()
        stop_event = threading.Event()

        def _spawn(layout: Layout) -> Tuple[str, int, float, Path]:
            log_path = log_dir / f"log.06-layout.{layout.name}.txt"
            with state_lock:
                state[layout.name].update(status="running",
                                           log_path=log_path,
                                           started_at=time.time())
            cmd = [_sys.executable, "-m", "graph_generation.cli",
                   "run", "layout",
                   "--config", str(config_path),
                   "--layouts", layout.name]
            with stopwatch() as elapsed:
                with log_path.open("w", encoding="utf-8") as logf:
                    rc = subprocess.run(
                        cmd, stdout=logf, stderr=subprocess.STDOUT,
                        env={**os.environ,
                             "PYTHONUNBUFFERED": "1",
                             # Outer parent rebuilds the viewer once
                             # at the end; child subprocesses skip it.
                             "PIPELINE_VIEWER_AUTOBUILD": "0"},
                    ).returncode
            with state_lock:
                state[layout.name]["status"] = (
                    "done" if rc == 0 else f"FAIL rc={rc}")
            return (layout.name, rc, elapsed(), log_path)

        def _dashboard(interval_s: float = 30.0) -> None:
            """Every ``interval_s`` seconds, print the latest tqdm
            progress line for every still-running layout."""
            while not stop_event.wait(interval_s):
                with state_lock:
                    snap = {k: dict(v) for k, v in state.items()}
                lines: List[str] = []
                for name, st in snap.items():
                    if st["status"] != "running" or not st["log_path"]:
                        continue
                    progress = _read_latest_progress(st["log_path"])
                    elapsed = time.time() - st["started_at"]
                    lines.append(f"  {name:<22s}  ({fmt_dur(elapsed)})  "
                                 f"{progress or '(starting up...)'}")
                if lines:
                    print("\n".join(["[layout progress]", *lines]),
                          flush=True)

        dash = threading.Thread(target=_dashboard, daemon=True)
        dash.start()

        _summary(f"[layout] dispatching {n} layouts across {cap} "
                 f"subprocesses; per-layout logs at "
                 f"log.06-layout.<name>.txt; summary at "
                 f"{summary_path.name}; progress snapshot every 30s")
        try:
            with ThreadPoolExecutor(max_workers=cap) as ex:
                futs = {ex.submit(_spawn, lyt): lyt for lyt in layouts}
                for fut in as_completed(futs):
                    name, rc, dt, log_path = fut.result()
                    n_done += 1
                    tag = f"{n_done:>2}/{n:<2}"
                    status = "ok" if rc == 0 else f"FAIL rc={rc}"
                    _summary(f"[layout] {tag}  {name:<22s} {status}  "
                             f"({fmt_dur(dt)})  → {log_path.name}")
        finally:
            stop_event.set()
            dash.join(timeout=2)
            summary_log.close()

    def _run_layout(self, ctx: PipelineContext, layout: Layout,
                    layout_ss: np.random.SeedSequence,
                    rows: List[Dict]) -> Dict[str, int]:
        # Pre-warm backend state in the parent so per-graph fork workers
        # inherit it via COW (no-op for layouts without timeout_s set).
        # Without this, every forked OGDF call would re-pay ~5s of cppyy
        # JIT compilation, blowing past the per-graph budget every time.
        prewarm(layout)

        # Per-graph seed is keyed by graph_id (NOT manifest position):
        # corpus reordering, sampling, or new sources do not perturb
        # the seed assigned to any existing graph.
        tasks = []
        for row in rows:
            sd = _per_graph_seed(layout_ss, row["graph_id"])
            graph_path = resolve_graph_path(ctx.out_dir, row)
            drawing_path = resolve_drawing_path(
                ctx.out_dir, layout.name, row,
            )
            tasks.append((str(graph_path), str(drawing_path), sd, row))

        # Manifest-side applicability filter — short-circuits before
        # any IO for layouts whose applies_to is fully determined by a
        # manifest column. The previous behaviour loaded every graphml
        # from disk just to discover ``is_tree`` was False (radial-tree)
        # or ``category`` was wrong (curated); on a 90k-row corpus that
        # cost ~20 min per layout per re-run for nothing.
        manifest_filter = getattr(layout, "manifest_applies_to", None)
        n_manifest_na = 0
        if manifest_filter is not None:
            kept = [t for t in tasks if manifest_filter(t[3])]
            n_manifest_na = len(tasks) - len(kept)
            tasks = kept
            if n_manifest_na:
                print(f"[layout] {layout.name}: {n_manifest_na:,} rows "
                      f"manifest-skipped (not applicable)",
                      flush=True)

        # Fused mode: skip the drawing-graphml round-trip and compute
        # metrics in-memory immediately after each layout. The metrics
        # CSV becomes the cache key (graph_id present ⇒ skip) instead
        # of the drawing file.
        write_drawings = ctx.config.layouts.write_drawings
        metric_names: List[str] = []
        cached_metric_ids: set = set()
        verify_ids: set = set()
        metrics_csv_path = None
        if not write_drawings:
            from .metrics import _selected_metrics
            from ._cleanup import clean_metric_csv, clean_metric_timings
            metric_names = _selected_metrics(ctx)
            metrics_csv_path = ctx.out_dir / "metrics" / f"{layout.name}.csv"
            # Same resume-hygiene pass the standalone metrics stage runs:
            # drop orphan rows whose graph_id is no longer in the
            # manifest, collapse interrupt-induced duplicates. The
            # returned set is the in-memory skip key — never re-read the
            # CSV after this point or we'd race with our own appends.
            valid_ids = {str(r["graph_id"]) for r in rows}
            cached_metric_ids = clean_metric_csv(metrics_csv_path, valid_ids)
            clean_metric_timings(
                ctx.out_dir / "_timings" / "metrics.csv",
                layout.name, valid_ids,
            )
            verify_n = ctx.config.layouts.verify_drawings_per_source
            verify_ids = _verify_ids(rows, verify_n)

        # Prioritise verify_ids — process them first so the visual
        # sample is on disk early, even if the run is interrupted.
        if verify_ids:
            tasks.sort(key=lambda t: t[3]["graph_id"] not in verify_ids)

        # Up-front cache breakdown — drives both the user-facing message
        # and the partition into ``work_tasks`` below so the tqdm bar
        # reflects resume state instead of crawling through cached
        # entries from 0%. The predicate mirrors the cache check inside
        # :func:`_run_one` so pre-filter and the safety-net check
        # agree:
        #   write_drawings=True : cached iff drawing file exists.
        #   write_drawings=False: cached iff metric row exists AND
        #     (not in verify_ids OR drawing file exists too). A verify
        #     graph with a metric row but no drawing must re-run so
        #     the visual sample lands on disk.
        if not write_drawings:
            def _cached(task) -> bool:
                gp, dp, _sd, row = task
                gid = row["graph_id"]
                if gid not in cached_metric_ids:
                    return False
                if gid in verify_ids and not Path(dp).exists():
                    return False
                return True
        else:
            def _cached(task) -> bool:
                return Path(task[1]).exists()

        work_tasks = [t for t in tasks if not _cached(t)]
        n_cache = len(tasks) - len(work_tasks)
        print(f"[layout] {layout.name}: {len(tasks):,} tasks "
              f"({n_cache:,} cached, {len(work_tasks):,} to compute)",
              flush=True)

        # Open the metrics CSV once and append per-row so an interrupt
        # mid-layout still leaves a usable partial CSV. Timings are
        # batched every 1000 rows to amortise the sidecar write.
        import csv as _csv
        from .metrics import _fmt
        from ..manifest import append_metric_timings
        metrics_file = None
        metrics_writer = None
        if metrics_csv_path is not None:
            metrics_csv_path.parent.mkdir(parents=True, exist_ok=True)
            is_fresh = (not metrics_csv_path.exists()
                          or metrics_csv_path.stat().st_size == 0)
            metrics_file = metrics_csv_path.open(
                "a", newline="", encoding="utf-8")
            metrics_writer = _csv.writer(metrics_file)
            if is_fresh:
                metrics_writer.writerow(["graph_id"] + metric_names)
                metrics_file.flush()

        n_ok = n_na = n_timeout = n_fail = 0
        # Cached entries are counted up-front from ``n_cache`` (the
        # partition computed above) so the summary reflects every
        # skipped graph, not just the ones :func:`_run_one` happens to
        # see if a file appears mid-run. The in-function cache check is
        # still a safety net — its returns add to ``n_cached``.
        n_cached = n_cache
        workers = max(1, int(ctx.config.parallel_workers))
        timings_batch: List[Dict] = []
        BATCH_SIZE = 1000

        def _flush_timings(force: bool = False) -> None:
            if not timings_batch:
                return
            if not force and len(timings_batch) < BATCH_SIZE:
                return
            append_metric_timings(ctx.out_dir, layout.name, timings_batch)
            timings_batch.clear()

        def _record(result):
            nonlocal n_ok, n_cached, n_na, n_timeout, n_fail
            gid, outcome, err, _, mvals, mtimes = result
            if outcome == _OUTCOME_OK:
                n_ok += 1
                if mvals and metrics_writer is not None:
                    metrics_writer.writerow(
                        [gid] + [_fmt(mvals.get(name, float("nan")))
                                 for name in metric_names])
                    metrics_file.flush()
                    timings_batch.append({"graph_id": gid,
                                           "timings": mtimes})
                    _flush_timings()
            elif outcome == _OUTCOME_SKIPPED_CACHED:
                n_cached += 1
            elif outcome == _OUTCOME_SKIPPED_NA:
                n_na += 1
            elif outcome == _OUTCOME_TIMEOUT:
                n_timeout += 1
                # Per-graph timeout line so the user can see *which*
                # graphs are eating the cap, not just the total count.
                print(f"\n[{layout.name}] {gid}: timeout ({err})",
                      file=sys.stderr, flush=True)
            else:
                n_fail += 1
                if err:
                    print(f"\n[{layout.name}] {gid}: {err}",
                          file=sys.stderr)

        try:
            # ``initial=n_cache`` pre-fills the bar so the percentage
            # reflects resume state immediately rather than crawling
            # from 0% through tens of thousands of cached entries.
            # ``total=len(tasks)`` keeps the denominator stable so the
            # bar still hits 100% at completion. We iterate only
            # ``work_tasks`` so a fully-cached layout's loop is a no-op.
            if workers == 1 or layout.backend != "native":
                for graph_path, drawing_path, sd, row in tqdm(
                        work_tasks, total=len(tasks), initial=n_cache,
                        unit="graph", desc=layout.name):
                    _record(_run_one(layout.name, graph_path, drawing_path, sd, row,
                                      write_drawings, metric_names, cached_metric_ids,
                                      verify_ids))
            else:
                with ProcessPoolExecutor(max_workers=workers) as ex:
                    futs = [
                        ex.submit(_run_one, layout.name, gp, dp, sd, row,
                                  write_drawings, metric_names, cached_metric_ids,
                                  verify_ids)
                        for gp, dp, sd, row in work_tasks
                    ]
                    for fut in tqdm(as_completed(futs),
                                      total=len(tasks), initial=n_cache,
                                      unit="graph", desc=layout.name):
                        _record(fut.result())
        finally:
            _flush_timings(force=True)
            if metrics_file is not None:
                metrics_file.close()

        # ``n_manifest_na`` are rows the manifest pre-filter dropped
        # before they ever became tasks — fold them into the n/a bucket
        # so the summary's column totals still match the manifest size.
        return {"ok": n_ok, "cached": n_cached,
                "na": n_na + n_manifest_na,
                "timeout": n_timeout, "fail": n_fail}
