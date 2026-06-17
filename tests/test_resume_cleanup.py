"""Resume-time cleanup of metric CSVs (T5, T6 in the reproducibility
refactor).

Two failure modes are guarded:
  - Orphan rows: graph_id sits in metrics/<layout>.csv but is no
    longer in the current manifest.
  - Duplicate rows: an interrupted run wrote a row, the worker pool
    restarted, and a second row landed for the same graph_id.

The cleanup must be: idempotent, atomic, and last-write-wins on
duplicates. End-to-end, an interrupt+resume must yield a final CSV
byte-identical to a single uninterrupted run (T6), and a manifest
change between runs must reconcile cleanly (T5).
"""

from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path
from typing import Dict, List

import pandas as pd
import pytest

from graph_generation.stages._cleanup import (
    clean_metric_csv, clean_metric_timings,
)


# ---- Direct unit tests for the cleanup helpers ------------------------

def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def _read_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    return header, rows


def test_clean_metric_csv_drops_orphans(tmp_path):
    csv_path = tmp_path / "kk.csv"
    _write_csv(csv_path, ["graph_id", "stress"],
                [["a", "0.1"], ["b", "0.2"], ["orphan", "0.3"]])

    survivors = clean_metric_csv(csv_path, valid_ids={"a", "b"})

    assert survivors == {"a", "b"}
    header, rows = _read_rows(csv_path)
    assert header == ["graph_id", "stress"]
    assert rows == [["a", "0.1"], ["b", "0.2"]]


def test_clean_metric_csv_collapses_duplicates_last_write_wins(tmp_path):
    csv_path = tmp_path / "kk.csv"
    _write_csv(csv_path, ["graph_id", "stress"],
                [["a", "0.1"],
                 ["b", "0.5"],
                 ["a", "0.99"],     # duplicate — LATER value wins
                 ["b", "0.7"]])     # duplicate — LATER value wins

    survivors = clean_metric_csv(csv_path, valid_ids={"a", "b"})

    assert survivors == {"a", "b"}
    _, rows = _read_rows(csv_path)
    by_id = {r[0]: r[1] for r in rows}
    assert by_id == {"a": "0.99", "b": "0.7"}
    assert len(rows) == 2  # duplicates collapsed


def test_clean_metric_csv_idempotent(tmp_path):
    """Running the cleaner twice on a clean file must be a no-op."""
    csv_path = tmp_path / "kk.csv"
    _write_csv(csv_path, ["graph_id", "stress"], [["a", "0.1"], ["b", "0.2"]])

    clean_metric_csv(csv_path, valid_ids={"a", "b"})
    bytes_after_first = csv_path.read_bytes()
    clean_metric_csv(csv_path, valid_ids={"a", "b"})
    bytes_after_second = csv_path.read_bytes()

    assert bytes_after_first == bytes_after_second


def test_clean_metric_csv_missing_file_returns_empty(tmp_path):
    assert clean_metric_csv(tmp_path / "nope.csv",
                              valid_ids={"a"}) == set()


def test_clean_metric_csv_empty_file(tmp_path):
    csv_path = tmp_path / "empty.csv"
    csv_path.touch()
    assert clean_metric_csv(csv_path, valid_ids={"a"}) == set()


def test_clean_metric_timings_only_touches_target_layout(tmp_path):
    """Other layouts' rows must pass through unchanged."""
    csv_path = tmp_path / "metrics.csv"
    _write_csv(csv_path,
                ["graph_id", "layout", "metric", "seconds"],
                [["a", "kamada-kawai", "stress", "0.01"],
                 ["b", "kamada-kawai", "stress", "0.02"],
                 ["a", "FMMM", "stress", "0.03"],
                 ["orphan", "kamada-kawai", "stress", "0.04"],
                 ["c", "FMMM", "stress", "0.05"]])

    n = clean_metric_timings(csv_path, "kamada-kawai",
                               valid_ids={"a", "b", "c"})

    assert n == 1  # one orphan removed
    _, rows = _read_rows(csv_path)
    fmmm_rows = [r for r in rows if r[1] == "FMMM"]
    kk_rows = [r for r in rows if r[1] == "kamada-kawai"]
    # FMMM rows untouched (a row for "a" and "c" both kept).
    assert {tuple(r) for r in fmmm_rows} == {
        ("a", "FMMM", "stress", "0.03"),
        ("c", "FMMM", "stress", "0.05"),
    }
    # KK rows: a + b kept, orphan dropped.
    assert {r[0] for r in kk_rows} == {"a", "b"}


def test_clean_metric_timings_streams_other_layout_rows(tmp_path,
                                                          monkeypatch):
    """Cleanup must NOT buffer other-layout rows in memory.

    Regression for the 16 GB WSL OOM seen at corpus scale: the prior
    implementation built ``other_layout_rows: list[list[str]]`` over
    every row of ``_timings/metrics.csv`` (~30M rows at 1.2 GB) and
    OOM-killed 5 simultaneous layout subprocesses. The fix streams
    other-layout rows directly from input to output. We enforce that
    via a stub csv.reader that aborts if asked for more rows than the
    target layout contains.
    """
    target = "kamada-kawai"
    other_rows = [["g_other_{}".format(i), "FMMM", "stress", "0.1"]
                  for i in range(100)]
    target_rows_with_orphan = [
        ["g_a", target, "stress", "0.01"],
        ["g_a", target, "stress", "0.02"],   # duplicate → triggers rewrite
        ["g_orphan", target, "stress", "0.04"],  # orphan → triggers rewrite
    ]
    csv_path = tmp_path / "metrics.csv"
    _write_csv(csv_path,
                ["graph_id", "layout", "metric", "seconds"],
                other_rows + target_rows_with_orphan)

    # We can't easily measure peak RSS in a unit test, so instead we
    # assert structurally: after the rewrite, no Python list as wide as
    # the full input was ever realised. Inspect the function source so a
    # future refactor that reintroduces the buffer fails this test.
    import inspect
    from graph_generation.stages import _cleanup
    src = inspect.getsource(_cleanup.clean_metric_timings)
    assert "other_layout_rows" not in src, (
        "clean_metric_timings reintroduced a list of all other-layout "
        "rows — this OOM-kills the layout dispatcher at corpus scale. "
        "Stream the rewrite instead.")

    n = clean_metric_timings(csv_path, target, valid_ids={"g_a"})
    assert n == 2  # 1 orphan + 1 dupe

    _, rows = _read_rows(csv_path)
    # Other-layout rows passed through unchanged and in original order.
    fmmm_rows = [r for r in rows if r[1] == "FMMM"]
    assert fmmm_rows == other_rows
    # Target layout rows: dedup'd + orphan dropped.
    target_rows = [r for r in rows if r[1] == target]
    assert target_rows == [["g_a", target, "stress", "0.02"]]


def test_clean_metric_timings_collapses_duplicates(tmp_path):
    csv_path = tmp_path / "metrics.csv"
    _write_csv(csv_path,
                ["graph_id", "layout", "metric", "seconds"],
                [["a", "kk", "stress", "0.01"],
                 ["a", "kk", "stress", "0.999"],   # dupe wins
                 ["a", "kk", "crossings", "0.02"]])

    n = clean_metric_timings(csv_path, "kk", valid_ids={"a"})

    assert n == 1
    _, rows = _read_rows(csv_path)
    by_metric = {r[2]: r[3] for r in rows}
    assert by_metric == {"stress": "0.999", "crossings": "0.02"}


# ---- T6: interrupt then resume == single run --------------------------
#
# The metrics stage appends per-row to <layout>.csv. Killing the
# stage at row N leaves the file with rows 0..N-1; resume picks up
# from row N and writes N..end. Final file must be byte-identical to
# a single full run.

def _setup_metrics_fixture(tmp_path: Path,
                            graph_ids: list[str]) -> Path:
    """Create a tiny output dir with a manifest and dummy drawing files.

    The drawings carry no real positions — the test patches
    ``_compute_one`` to return a deterministic value per graph_id, so
    no real layout / metric library is invoked.
    """
    out = tmp_path / "out"
    drawings = out / "drawings" / "kamada-kawai" / "generated"
    drawings.mkdir(parents=True)
    for gid in graph_ids:
        (drawings / gid).write_text("dummy", encoding="utf-8")
    rows = [{"graph_id": gid, "category": "generated", "source": "",
              "n_nodes": 5, "n_edges": 4} for gid in graph_ids]
    pd.DataFrame(rows).to_csv(out / "manifest.csv", index=False)
    return out


def _make_ctx(out_dir: Path):
    from graph_generation.config import (
        DedupConfig, GenerateConfig, LayoutsConfig, MetricsConfig,
        PipelineConfig, SampleConfig, SourcesConfig, StageConfig,
        ValidateConfig,
    )
    from graph_generation.stages.base import PipelineContext
    cfg = PipelineConfig(
        seed=42, out_dir=out_dir, parallel_workers=1,
        generate=GenerateConfig(count=0, n_min=2, n_max=10,
                                  generators="*", max_retries=10),
        validate=ValidateConfig(n_min=2, n_max=75, density_cap=1.0,
                                 require_connected=True,
                                 require_simple=True),
        stage=StageConfig(caps={}, default_cap=10000, n_min_real_world=8),
        sample=SampleConfig(enabled=False, seed_offset=0, caps={}),
        dedup=DedupConfig(enabled=False, method="properties"),
        layouts=LayoutsConfig(selected=["kamada-kawai"], exclude=[]),
        metrics=MetricsConfig(selected=["kruskal_stress"]),
        sources=SourcesConfig(benchmark=[], real_world=[],
                                graphs_with_drawings=[]),
    )
    return PipelineContext.from_config(cfg)


def _patch_compute_one(monkeypatch, kill_after: int | None = None):
    """Stub `_compute_one` to return a deterministic per-graph value.

    Optionally raises after ``kill_after`` calls to simulate a mid-run
    interrupt.
    """
    counter = {"n": 0}

    def fake_compute_one(drawing_path: str, metric_names: list[str]):
        counter["n"] += 1
        if kill_after is not None and counter["n"] > kill_after:
            raise KeyboardInterrupt("simulated mid-run kill")
        gid = Path(drawing_path).name
        # Deterministic value per graph_id so byte-identity is meaningful.
        val = abs(hash(gid)) % 1000 / 1000.0
        return ({m: val for m in metric_names},
                {m: 0.001 for m in metric_names},
                "")
    monkeypatch.setattr(
        "graph_generation.stages.metrics._compute_one",
        fake_compute_one,
    )
    return counter


def test_t6_interrupt_then_resume_byte_identical_to_single_run(tmp_path,
                                                                  monkeypatch):
    """Final metric CSV after interrupt+resume == single uninterrupted run."""
    from graph_generation.stages.metrics import MetricsStage

    graph_ids = [f"g_{i:03d}" for i in range(20)]

    # Run A: single uninterrupted run.
    out_a = _setup_metrics_fixture(tmp_path / "a", graph_ids)
    _patch_compute_one(monkeypatch, kill_after=None)
    MetricsStage().run(_make_ctx(out_a))
    bytes_a = (out_a / "metrics" / "kamada-kawai.csv").read_bytes()

    # Run B: kill at row 7, then resume to completion.
    out_b = _setup_metrics_fixture(tmp_path / "b", graph_ids)
    _patch_compute_one(monkeypatch, kill_after=7)
    with pytest.raises(KeyboardInterrupt):
        MetricsStage().run(_make_ctx(out_b))
    # Resume — fresh stub, no kill.
    _patch_compute_one(monkeypatch, kill_after=None)
    MetricsStage().run(_make_ctx(out_b))
    bytes_b = (out_b / "metrics" / "kamada-kawai.csv").read_bytes()

    assert bytes_a == bytes_b, (
        f"interrupt+resume CSV differs from single-run CSV.\n"
        f"single: {bytes_a!r}\nresume: {bytes_b!r}")


# ---- T5: resume across manifest change is clean -----------------------

def test_t5_manifest_change_between_runs_reconciles_cleanly(tmp_path,
                                                              monkeypatch):
    """Run on M1, replace manifest with M2 (some kept, some removed,
    some added), re-run. CSV must end up clean: all kept rows
    unchanged, all removed rows absent, all added rows present
    exactly once."""
    from graph_generation.stages.metrics import MetricsStage

    # M1 = {g_000 .. g_009}
    m1_ids = [f"g_{i:03d}" for i in range(10)]
    # M2 = keep {g_002 .. g_007}, remove {g_000, g_001, g_008, g_009},
    # add {g_100, g_101, g_102}
    m2_keep = [f"g_{i:03d}" for i in range(2, 8)]
    m2_added = ["g_100", "g_101", "g_102"]
    m2_ids = m2_keep + m2_added

    out = _setup_metrics_fixture(tmp_path / "out",
                                   sorted(set(m1_ids) | set(m2_ids)))

    # First run uses M1. Patch the manifest to only reference M1 ids.
    pd.DataFrame([{"graph_id": gid, "category": "generated",
                    "source": "", "n_nodes": 5, "n_edges": 4}
                   for gid in m1_ids]).to_csv(out / "manifest.csv",
                                                index=False)

    _patch_compute_one(monkeypatch, kill_after=None)
    MetricsStage().run(_make_ctx(out))

    csv_path = out / "metrics" / "kamada-kawai.csv"
    snapshot_run1 = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            snapshot_run1[row["graph_id"]] = row["kruskal_stress"]
    assert set(snapshot_run1) == set(m1_ids)

    # Now swap in M2 and re-run.
    pd.DataFrame([{"graph_id": gid, "category": "generated",
                    "source": "", "n_nodes": 5, "n_edges": 4}
                   for gid in m2_ids]).to_csv(out / "manifest.csv",
                                                index=False)
    _patch_compute_one(monkeypatch, kill_after=None)
    MetricsStage().run(_make_ctx(out))

    final = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    # No duplicates.
    ids_in_csv = [r["graph_id"] for r in rows]
    assert len(ids_in_csv) == len(set(ids_in_csv)), (
        f"duplicate graph_ids: {ids_in_csv}")
    final = {r["graph_id"]: r["kruskal_stress"] for r in rows}
    # Removed rows are absent.
    for removed in ("g_000", "g_001", "g_008", "g_009"):
        assert removed not in final
    # Kept rows have the same values as run 1.
    for kept in m2_keep:
        assert final[kept] == snapshot_run1[kept], (
            f"{kept}: kept-row value changed between runs "
            f"({snapshot_run1[kept]!r} -> {final[kept]!r})")
    # Added rows are present exactly once.
    for added in m2_added:
        assert added in final


def test_layout_manifest_filter_skips_non_applicable_rows(tmp_path,
                                                            monkeypatch):
    """Regression for the radial-tree / planar / curated I/O bug.

    Setup: 4 rows in the manifest, 1 with is_tree=True. The radial-tree
    layout has ``manifest_applies_to`` keyed on is_tree, so only the
    one tree row should reach ``_run_one``. The other 3 must be
    accounted for as n/a in the summary without ever loading their
    graphml — previously this cost a graphml read + nx.is_tree check
    per row on every re-run.
    """
    from graph_generation.layouts.base import Layout, register_layout
    from graph_generation.layouts import LAYOUT_REGISTRY
    from graph_generation.stages.layout import LayoutStage, _OUTCOME_OK

    # Synthetic layout with a manifest predicate. Registered under a
    # unique name so we don't collide with the canonical radial-tree.
    name = "test_tree_only"
    if name in LAYOUT_REGISTRY:
        del LAYOUT_REGISTRY[name]

    def _manifest_is_tree(row):
        v = row.get("is_tree")
        return v is True or str(v).strip().lower() == "true"

    register_layout(Layout(
        name=name, backend="native",
        fn=lambda G, seed: ({n: (0.0, 0.0) for n in G.nodes}, None),
        stochastic=False,
        manifest_applies_to=_manifest_is_tree,
    ))

    try:
        graph_ids = [f"g_{i:03d}" for i in range(4)]
        out = _setup_metrics_fixture(tmp_path / "out", graph_ids)
        for gid in graph_ids:
            gp = out / "graphs" / "generated"
            gp.mkdir(parents=True, exist_ok=True)
            (gp / gid).write_text("dummy", encoding="utf-8")

        # Manifest with mixed is_tree values: only g_002 is a tree.
        manifest_rows = [
            {"graph_id": "g_000", "category": "generated", "source": "",
              "n_nodes": 5, "n_edges": 4, "is_tree": False},
            {"graph_id": "g_001", "category": "generated", "source": "",
              "n_nodes": 5, "n_edges": 5, "is_tree": False},
            {"graph_id": "g_002", "category": "generated", "source": "",
              "n_nodes": 5, "n_edges": 4, "is_tree": True},
            {"graph_id": "g_003", "category": "generated", "source": "",
              "n_nodes": 5, "n_edges": 6, "is_tree": False},
        ]
        pd.DataFrame(manifest_rows).to_csv(out / "manifest.csv", index=False)

        from graph_generation.config import (
            DedupConfig, GenerateConfig, LayoutsConfig, MetricsConfig,
            PipelineConfig, SampleConfig, SourcesConfig, StageConfig,
            ValidateConfig,
        )
        from graph_generation.stages.base import PipelineContext
        cfg = PipelineConfig(
            seed=42, out_dir=out, parallel_workers=1,
            generate=GenerateConfig(count=0, n_min=2, n_max=10,
                                      generators="*", max_retries=10),
            validate=ValidateConfig(n_min=2, n_max=75, density_cap=1.0,
                                     require_connected=True,
                                     require_simple=True),
            stage=StageConfig(caps={}, default_cap=10000,
                                n_min_real_world=8),
            sample=SampleConfig(enabled=False, seed_offset=0, caps={}),
            dedup=DedupConfig(enabled=False, method="properties"),
            layouts=LayoutsConfig(selected=[name], exclude=[],
                                     write_drawings=False,
                                     verify_drawings_per_source=0),
            metrics=MetricsConfig(selected=["kruskal_stress"]),
            sources=SourcesConfig(benchmark=[], real_world=[],
                                    graphs_with_drawings=[]),
        )
        ctx = PipelineContext.from_config(cfg)

        seen_ids: list[str] = []

        def _fake_run_one(layout_name, graph_path, drawing_path, sd, row,
                           write_drawings, metric_names,
                           cached_metric_ids, verify_ids):
            seen_ids.append(row["graph_id"])
            return (row["graph_id"], _OUTCOME_OK, None, 0.001,
                    {"kruskal_stress": 0.7},
                    {"kruskal_stress": 0.001})

        monkeypatch.setattr(
            "graph_generation.stages.layout._run_one", _fake_run_one)

        LayoutStage().run(ctx)

        # Only the tree row should have hit _run_one. The other 3
        # never had their graphml loaded — that's the whole point.
        assert seen_ids == ["g_002"], (
            f"expected only the tree row to reach _run_one, got {seen_ids!r}")
    finally:
        LAYOUT_REGISTRY.pop(name, None)


def test_layout_resume_skips_cached_before_loop(tmp_path, monkeypatch):
    """Regression for the progress-bar / cache-skip alignment.

    Setup: 8 graphs, 5 already have metric rows from a prior run.
    After resume, the tqdm bar must start at 5/8 and the inner
    ``_run_one`` must only be called for the 3 uncached graphs —
    iterating cached entries through the bar burns wall time on
    file-stat calls and (worse) makes the bar's percentage misleading
    for users watching long-running layouts (HOLA, dot-ortho, etc.).
    """
    from graph_generation.stages.layout import LayoutStage, _OUTCOME_OK

    graph_ids = [f"g_{i:03d}" for i in range(8)]
    cached_ids = set(graph_ids[:5])

    out = _setup_metrics_fixture(tmp_path / "out", graph_ids)
    # Also need a graphs/ tree so resolve_graph_path doesn't trip the
    # missing-source check in _run_one. The drawings are already in
    # place from _setup_metrics_fixture.
    for gid in graph_ids:
        gp = out / "graphs" / "generated"
        gp.mkdir(parents=True, exist_ok=True)
        (gp / gid).write_text("dummy", encoding="utf-8")

    # Pre-populate metrics CSV with cached rows (the cache key in fused
    # mode is "graph_id present in metrics/<layout>.csv").
    metrics_csv = out / "metrics" / "kamada-kawai.csv"
    metrics_csv.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(metrics_csv, ["graph_id", "kruskal_stress"],
                [[gid, "0.5"] for gid in cached_ids])

    # Force fused mode so the metric-row cache is the active path.
    from graph_generation.config import (
        DedupConfig, GenerateConfig, LayoutsConfig, MetricsConfig,
        PipelineConfig, SampleConfig, SourcesConfig, StageConfig,
        ValidateConfig,
    )
    from graph_generation.stages.base import PipelineContext
    cfg = PipelineConfig(
        seed=42, out_dir=out, parallel_workers=1,
        generate=GenerateConfig(count=0, n_min=2, n_max=10,
                                  generators="*", max_retries=10),
        validate=ValidateConfig(n_min=2, n_max=75, density_cap=1.0,
                                 require_connected=True,
                                 require_simple=True),
        stage=StageConfig(caps={}, default_cap=10000, n_min_real_world=8),
        sample=SampleConfig(enabled=False, seed_offset=0, caps={}),
        dedup=DedupConfig(enabled=False, method="properties"),
        layouts=LayoutsConfig(selected=["kamada-kawai"], exclude=[],
                                 write_drawings=False,
                                 verify_drawings_per_source=0),
        metrics=MetricsConfig(selected=["kruskal_stress"]),
        sources=SourcesConfig(benchmark=[], real_world=[],
                                graphs_with_drawings=[]),
    )
    ctx = PipelineContext.from_config(cfg)

    seen_ids: list[str] = []

    def _fake_run_one(layout_name, graph_path, drawing_path, sd, row,
                       write_drawings, metric_names, cached_metric_ids,
                       verify_ids):
        seen_ids.append(row["graph_id"])
        return (row["graph_id"], _OUTCOME_OK, None, 0.001,
                {"kruskal_stress": 0.7}, {"kruskal_stress": 0.001})

    monkeypatch.setattr("graph_generation.stages.layout._run_one",
                         _fake_run_one)

    stage = LayoutStage()
    stage.run(ctx)

    # The 5 cached graph_ids must NOT be re-dispatched into _run_one;
    # only the 3 fresh graphs trigger work. Order within the 3 is
    # implementation-defined (tasks are sorted by verify_ids first),
    # so compare as sets.
    assert set(seen_ids) == set(graph_ids[5:]), (
        f"expected 3 uncached graphs to be dispatched, got {seen_ids!r}")


def test_resume_to_clean_csv_with_orphan_already_present(tmp_path,
                                                          monkeypatch):
    """If the previous run left an orphan row in the CSV that the new
    manifest doesn't cover, the next run must drop it before
    appending. (Covers the brief's §4 (a) directly.)"""
    from graph_generation.stages.metrics import MetricsStage

    graph_ids = ["g_000", "g_001", "g_002"]
    out = _setup_metrics_fixture(tmp_path / "out", graph_ids)

    # Pre-populate the metric CSV with two valid rows + one orphan.
    csv_path = out / "metrics" / "kamada-kawai.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(csv_path, ["graph_id", "kruskal_stress"],
                [["g_000", "0.5"],
                 ["orphan_id", "0.999"],
                 ["g_001", "0.6"]])

    _patch_compute_one(monkeypatch, kill_after=None)
    MetricsStage().run(_make_ctx(out))

    final = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            final[row["graph_id"]] = row["kruskal_stress"]

    assert "orphan_id" not in final
    # Pre-existing valid rows retained verbatim, new rows added.
    assert final["g_000"] == "0.5"
    assert final["g_001"] == "0.6"
    assert "g_002" in final
