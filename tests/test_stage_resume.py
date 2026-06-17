"""Resume contract for the stage stage.

Re-runs on a previously-staged corpus must skip every graph_id that
was already accepted (in the live manifest) AND every graph_id that
the dedup or sample stages previously dropped (recorded in the
``manifest.dedup-audit.csv`` and ``manifest.sampling-audit.csv``
sidecars). Without the audit-feedback loop, dropped graphs get
re-staged on every run and dedup/sample re-drop them — a write/unlink
churn that doesn't change the final corpus.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, List

import networkx as nx
import pandas as pd

from graph_generation.config import ValidateConfig
from graph_generation.sources import Source
from graph_generation.stagers.base import Stager, StagedGraph
from graph_generation.stages.stage import (
    _existing_ids,
    _is_source_complete,
    _mark_source_complete,
    _sentinel_path,
)


_VC = ValidateConfig(
    n_min=2, n_max=75, density_cap=1.0,
    require_connected=True, require_simple=True,
)


def _src(name: str = "fake", category: str = "real_world") -> Source:
    return Source(name=name, category=category, description="",
                   citation="", url=None, archive_name=None,
                   strip_prefix=None, staging_path=None)


class _FakeStager(Stager):
    source_name = "fake"

    def __init__(self, *args, sequence: List[int], **kwargs):
        kwargs.setdefault("validate_config", _VC)
        super().__init__(*args, **kwargs)
        self._sequence = sequence
        self.iterated = 0

    def graphs(self) -> Iterator[StagedGraph]:
        for i, n in enumerate(self._sequence):
            self.iterated += 1
            yield StagedGraph(name=f"g{i}", graph=nx.path_graph(n))

    def target_dir(self) -> Path:
        return self.out_dir


def _write_manifest(path: Path, graph_ids: List[str]) -> None:
    pd.DataFrame({"graph_id": graph_ids}).to_csv(path, index=False)


def _write_audit(path: Path, dropped_ids: List[str]) -> None:
    pd.DataFrame({"dropped_graph_id": dropped_ids}).to_csv(path, index=False)


def test_existing_ids_returns_empty_for_missing_manifest(tmp_path):
    assert _existing_ids(tmp_path / "nope.csv") == set()


def test_existing_ids_unions_manifest_and_audits(tmp_path):
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, ["a", "b", "c"])
    _write_audit(manifest.with_name("manifest.dedup-audit.csv"),
                 ["d_drop", "e_drop"])
    _write_audit(manifest.with_name("manifest.sampling-audit.csv"),
                 ["f_drop"])
    assert _existing_ids(manifest) == {"a", "b", "c",
                                        "d_drop", "e_drop", "f_drop"}


def test_existing_ids_tolerates_missing_audits(tmp_path):
    """Manifest present, neither audit yet — must not crash."""
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, ["only_one"])
    assert _existing_ids(manifest) == {"only_one"}


def test_existing_ids_tolerates_nan_graph_ids(tmp_path):
    """A NaN graph_id row in either file is dropped silently."""
    manifest = tmp_path / "manifest.csv"
    pd.DataFrame({"graph_id": ["a", None, "b"]}).to_csv(manifest, index=False)
    _write_audit(manifest.with_name("manifest.dedup-audit.csv"),
                 ["c_drop"])
    assert _existing_ids(manifest) == {"a", "b", "c_drop"}


def test_sentinel_absent_means_not_complete(tmp_path):
    """Fresh out_dir has no sentinels; nothing is treated as complete."""
    assert not _is_source_complete(tmp_path, "houseofgraphs",
                                    n_min=8, n_max=75, max_graphs=10000)


def test_sentinel_roundtrip_matches_bounds(tmp_path):
    """Marking a source complete and reading it back under the same
    bounds reports complete; under different bounds reports incomplete.
    The (n_min, n_max, max_graphs) tuple becomes the cache key so a
    config change invalidates the marker without manual cleanup."""
    _mark_source_complete(tmp_path, "houseofgraphs",
                           n_min=8, n_max=75, max_graphs=10000,
                           kept=10000, cap_reached=True)
    assert _is_source_complete(tmp_path, "houseofgraphs",
                                n_min=8, n_max=75, max_graphs=10000)
    # Tighter cap → re-run.
    assert not _is_source_complete(tmp_path, "houseofgraphs",
                                    n_min=8, n_max=75, max_graphs=5000)
    # Different n_max → re-run.
    assert not _is_source_complete(tmp_path, "houseofgraphs",
                                    n_min=8, n_max=100, max_graphs=10000)


def test_sentinel_path_filesystem_safe_for_slash_sources(tmp_path):
    """TUDataset/<NAME> sources hit a stager registered under the
    ``TUDataset/`` prefix. The sentinel filename must not contain the
    slash or it would create an unintended subdirectory."""
    p = _sentinel_path(tmp_path, "TUDataset/MUTAG")
    assert p.name == "TUDataset_MUTAG.json"
    assert p.parent.name == "_completed"


def test_sentinel_corrupt_json_is_not_complete(tmp_path):
    """A truncated / unparseable sentinel should not block a re-run —
    treat it as missing and re-stage the source so we can rewrite it."""
    path = _sentinel_path(tmp_path, "houseofgraphs")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert not _is_source_complete(tmp_path, "houseofgraphs",
                                    n_min=8, n_max=75, max_graphs=10000)


def test_stager_skips_ids_from_dedup_audit(tmp_path):
    """End-to-end: a stager fed dedup-audit IDs via existing_ids must
    early-skip those graphs at the per-graph dedup gate, not write them
    to disk and not return manifest rows for them."""
    # The base class builds graph_ids as ``<source>_<stem>.graphml``,
    # i.e. for source 'fake' and stem 'g1' the id is 'fake_g1.graphml'.
    pre_dropped = {"fake_g1.graphml", "fake_g3.graphml"}
    s = _FakeStager(_src(), tmp_path,
                     n_min=2, n_max=75, max_graphs=0,
                     existing_ids=pre_dropped,
                     sequence=[10, 12, 14, 16])  # g0..g3
    r = s.stage()
    # Two of four graphs were in the (simulated) audit set.
    assert r.kept == 2
    assert r.reasons.get("already_in_manifest") == 2
    # Only the un-skipped graphs end up in manifest_rows / on disk.
    kept_ids = {row["graph_id"] for row in r.manifest_rows}
    assert kept_ids == {"fake_g0.graphml", "fake_g2.graphml"}
    # The skipped ones were NOT written to disk.
    for skipped in pre_dropped:
        assert not (tmp_path / skipped).exists()
