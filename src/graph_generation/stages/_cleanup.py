"""Resume-time CSV cleanup for the layout / metrics stages.

The pipeline's resume contract treats "graph_id present in metric CSV"
as the cache key. Two failure modes break that contract when the
manifest changes between runs:

  - Orphan rows: a graph_id sits in ``metrics/<layout>.csv`` but is
    no longer in the current manifest (e.g. dropped by sample, or a
    source removed from the config). Subsequent reads see the orphan
    and silently keep it.
  - Duplicate rows: an interrupted run wrote a row, the worker pool
    restarted, and the new run wrote a second row for the same
    graph_id with possibly different values (especially before the
    seed cascade was made graph_id-keyed).

This module owns the rewrite logic. Call :func:`clean_metric_csv` once
at the top of each per-layout run; it returns the in-memory set of
valid graph_ids so the caller can use that as the skip key without
re-reading the file (which would race with subsequent appends).
"""

from __future__ import annotations

import csv
import os
import sys
import time
from pathlib import Path
from typing import Iterable, Set


def _atomic_replace(src: Path, dst: Path, attempts: int = 5,
                     delay_s: float = 0.05) -> None:
    """``src.replace(dst)`` with a brief retry on ``FileNotFoundError``.

    Mirrors the retry the layout stage uses for graphml output. drvfs
    (WSL ↔ NTFS) sometimes returns ENOENT on a freshly-written file
    under contention; a few retries side-step the race.
    """
    for i in range(attempts):
        try:
            src.replace(dst)
            return
        except FileNotFoundError:
            if i == attempts - 1:
                raise
            time.sleep(delay_s * (i + 1))


def clean_metric_csv(csv_path: Path,
                     valid_ids: Iterable[str]) -> Set[str]:
    """Drop orphan & duplicate rows from a per-layout metric CSV.

    Returns the set of graph_ids that survived the clean — use this as
    the cache-skip key for the rest of the run. Reading the file again
    later would race with the run's own appends, so the in-memory set
    is the only safe source of truth.

    Cleanup rules:
      - A row whose ``graph_id`` is not in ``valid_ids`` is dropped
        (orphan from a previous-corpus run).
      - Duplicate ``graph_id`` rows collapse to the LAST occurrence in
        the file (last-write-wins — newer runs override older ones).
      - The header is preserved unchanged. Other columns are passed
        through verbatim — the cleaner is metric-agnostic.

    The rewrite is atomic: the cleaned content is written to
    ``<csv>.cleanup.tmp`` then renamed over the original. If no rows
    are dropped or collapsed, the file is left untouched (idempotent
    no-op).

    A one-line summary of what was pruned is printed to stderr so the
    user has a record in the run log.
    """
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return set()

    valid = set(valid_ids)
    keep: dict[str, list[str]] = {}  # last-write-wins per graph_id
    header: list[str] | None = None
    n_orphans = 0
    n_total = 0
    n_dupes_collapsed = 0
    seen_at_least_once: set[str] = set()

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return set()
        try:
            gid_col = header.index("graph_id")
        except ValueError:
            # No graph_id column — bail out cleanly. The caller's normal
            # parse path will surface the malformed file.
            return set()
        for row in reader:
            if not row:
                continue
            n_total += 1
            if gid_col >= len(row):
                continue
            gid = row[gid_col]
            if gid not in valid:
                n_orphans += 1
                continue
            if gid in seen_at_least_once:
                n_dupes_collapsed += 1
            seen_at_least_once.add(gid)
            keep[gid] = row  # last write wins

    if n_orphans == 0 and n_dupes_collapsed == 0:
        # Idempotent fast path: nothing to rewrite.
        return set(keep)

    tmp = csv_path.with_suffix(csv_path.suffix + ".cleanup.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in keep.values():
            writer.writerow(row)
        f.flush()
        try:
            os.fsync(f.fileno())
        except (OSError, AttributeError):
            pass
    _atomic_replace(tmp, csv_path)

    print(f"[cleanup] {csv_path.name}: pruned {n_orphans} orphan rows, "
          f"collapsed {n_dupes_collapsed} duplicate rows "
          f"(kept {len(keep)} of {n_total})",
          file=sys.stderr, flush=True)
    return set(keep)


def clean_metric_timings(timings_csv: Path, layout: str,
                          valid_ids: Iterable[str]) -> int:
    """Drop orphan/duplicate timing rows for one layout.

    The shared ``_timings/metrics.csv`` covers every (graph_id, layout,
    metric) combination. Cleaning is per-layout: rows with
    ``layout == layout`` whose ``graph_id`` is no longer valid are
    dropped, and duplicates collapse to last-write-wins per
    (graph_id, layout, metric). Rows for OTHER layouts are passed
    through untouched.

    Returns the number of rows pruned (orphan + duplicate). Idempotent
    — repeat calls on a clean file are a no-op.

    Memory: the prior implementation buffered the entire other-layouts
    slice in a Python list, which is fine for kilobyte CSVs but OOM-
    killed the layout dispatcher once the corpus's ``_timings/metrics.csv``
    grew past ~1 GB (≈30M rows × ~300 B Python overhead ≈ 9 GB per
    subprocess; 5 simultaneous subprocesses OOM'd a 16 GB WSL). The
    two-pass design below holds only this layout's rows in memory
    (≈1/19 of the file) and streams the others through to disk.
    """
    if not timings_csv.exists() or timings_csv.stat().st_size == 0:
        return 0

    valid = set(valid_ids)

    # Pass 1 — inspect only this layout's rows. Other-layout rows are
    # counted but not buffered; pass 2 streams them back through if a
    # rewrite turns out to be needed.
    keep_for_layout: dict[tuple[str, str], list[str]] = {}
    n_orphans = 0
    n_dupes = 0
    header: list[str] | None = None
    gid_col = lyt_col = met_col = -1

    with timings_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return 0
        try:
            gid_col = header.index("graph_id")
            lyt_col = header.index("layout")
            met_col = header.index("metric")
        except ValueError:
            return 0
        max_col = max(gid_col, lyt_col, met_col)
        for row in reader:
            if not row or max_col >= len(row):
                continue
            if row[lyt_col] != layout:
                continue
            gid = row[gid_col]
            if gid not in valid:
                n_orphans += 1
                continue
            key = (gid, row[met_col])
            if key in keep_for_layout:
                n_dupes += 1
            keep_for_layout[key] = row

    if n_orphans == 0 and n_dupes == 0:
        return 0

    # Pass 2 — rewrite. Stream other-layout rows from input → output
    # so peak memory stays at ~keep_for_layout size, not the whole file.
    tmp = timings_csv.with_suffix(timings_csv.suffix + ".cleanup.tmp")
    with timings_csv.open(newline="", encoding="utf-8") as f_in, \
            tmp.open("w", newline="", encoding="utf-8") as f_out:
        reader = csv.reader(f_in)
        writer = csv.writer(f_out)
        next(reader, None)  # discard old header
        writer.writerow(header)
        max_col = max(gid_col, lyt_col, met_col)
        for row in reader:
            if not row or max_col >= len(row):
                continue
            # Pass other layouts through unchanged. Drop this-layout
            # rows here — they're re-emitted from keep_for_layout below
            # so duplicates collapse to last-write-wins.
            if row[lyt_col] != layout:
                writer.writerow(row)
        for row in keep_for_layout.values():
            writer.writerow(row)
        f_out.flush()
        try:
            os.fsync(f_out.fileno())
        except (OSError, AttributeError):
            pass
    _atomic_replace(tmp, timings_csv)

    print(f"[cleanup] {timings_csv.name}/{layout}: pruned {n_orphans} "
          f"orphan timing rows, collapsed {n_dupes} duplicates",
          file=sys.stderr, flush=True)
    return n_orphans + n_dupes
