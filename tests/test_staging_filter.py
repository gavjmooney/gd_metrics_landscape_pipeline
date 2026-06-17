"""Stager base-class size filter + content filter + per-source cap.

A fake stager yields a deterministic mix of in-bounds, out-of-bounds,
and many-of-the-same graphs. The base class is expected to:
  - drop graphs whose n is outside [n_min, n_max] without writing,
  - drop disconnected graphs (content filter),
  - stop iterating after ``max_graphs`` writes (cap reached),
  - call the ``_write`` hook so subclasses can customise output format,
  - return a :class:`StageResult` with the per-source funnel and rows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, List

import networkx as nx

from graph_generation.config import ValidateConfig
from graph_generation.sources import Source
from graph_generation.stagers.base import Stager, StagedGraph


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
        self.written: list[Path] = []

    def graphs(self) -> Iterator[StagedGraph]:
        for i, n in enumerate(self._sequence):
            self.iterated += 1
            yield StagedGraph(name=f"g{i}", graph=nx.path_graph(n))

    def target_dir(self) -> Path:
        # Override so the fake stager's category-aware path resolution
        # doesn't try to create graphs/<category>/<name>/ subtrees.
        return self.out_dir

    def _write(self, G: nx.Graph, path: Path) -> None:
        self.written.append(path)
        super()._write(G, path)


def test_size_filter_drops_out_of_bounds(tmp_path):
    sizes = [1, 5, 8, 50, 75, 76, 200]
    s = _FakeStager(_src(), tmp_path,
                     n_min=8, n_max=75, max_graphs=0,
                     sequence=sizes)
    r = s.stage()
    assert r.kept == 3   # 8, 50, 75
    assert r.reasons.get("out_of_size") == 4
    assert len(s.written) == 3


def test_max_graphs_cap_stops_iteration_early(tmp_path):
    s = _FakeStager(_src(), tmp_path,
                     n_min=8, n_max=75, max_graphs=4,
                     sequence=[10] * 100)
    r = s.stage()
    assert r.kept == 4
    assert r.cap_reached is True
    # Iteration should stop right after the 4th write — not run the
    # whole 100-element sequence.
    assert s.iterated == 4


def test_cap_zero_means_unlimited(tmp_path):
    s = _FakeStager(_src(), tmp_path,
                     n_min=2, n_max=200, max_graphs=0,
                     sequence=[10] * 50)
    r = s.stage()
    assert r.kept == 50
    assert r.cap_reached is False


def test_size_filter_runs_before_cap(tmp_path):
    # 5 oversize then 3 in-bounds — cap=2 should keep 2 of the 3,
    # not be exhausted by oversize ones.
    s = _FakeStager(_src(), tmp_path,
                     n_min=8, n_max=75, max_graphs=2,
                     sequence=[200, 200, 200, 200, 200, 10, 12, 14])
    r = s.stage()
    assert r.kept == 2
    # All 5 oversize were iterated, plus the first 2 in-bounds.
    assert s.iterated == 5 + 2


def test_content_filter_rejects_disconnected(tmp_path):
    """A graph with two components fails the connected check."""
    class _TwoCompStager(_FakeStager):
        def graphs(self):
            self.iterated = 1
            G = nx.Graph()
            G.add_edges_from([(0, 1), (2, 3)])
            yield StagedGraph(name="disc", graph=G)
    s = _TwoCompStager(_src(), tmp_path,
                       n_min=2, n_max=75, max_graphs=0,
                       sequence=[])
    r = s.stage()
    assert r.kept == 0
    assert r.reasons.get("disconnected") == 1


def test_manifest_rows_carry_properties(tmp_path):
    s = _FakeStager(_src(), tmp_path,
                     n_min=2, n_max=75, max_graphs=0,
                     sequence=[10])
    r = s.stage()
    assert len(r.manifest_rows) == 1
    row = r.manifest_rows[0]
    assert row["graph_id"] == "fake_g0.graphml"
    assert row["category"] == "real_world"
    assert row["n_nodes"] == 10
    # timing row should pair up
    assert len(r.timing_rows) == 1
    assert r.timing_rows[0]["graph_id"] == "fake_g0.graphml"
    assert "diameter" in r.timing_rows[0]["timings"]


def test_write_hook_overrides_format(tmp_path):
    class _MarkerStager(_FakeStager):
        def _write(self, G: nx.Graph, path: Path) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"n={G.number_of_nodes()}")
            self.written.append(path)

    s = _MarkerStager(_src(), tmp_path,
                       n_min=2, n_max=75, max_graphs=0,
                       sequence=[5, 10])
    s.stage()
    assert all(p.read_text().startswith("n=") for p in s.written)
