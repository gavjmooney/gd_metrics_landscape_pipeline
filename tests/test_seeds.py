"""Seed cascade keying contract.

Per-graph and per-layout seeds must be pure functions of (root_seed,
layout_name, graph_id) — independent of any sibling stream's existence.
This is the precondition for reproducibility under corpus drift
(adding/removing layouts or graphs without re-rolling unrelated seeds).

Also covers the per-source independence used by the sample stage and
the no-perturbation property of registering a new layout.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from graph_generation import seeds
from graph_generation.stages.layout import _per_graph_seed
from graph_generation.stages.sample import _seed_for_source


# ---- T1: per-graph seed is graph_id-keyed -----------------------------

def test_per_graph_seed_is_graph_id_keyed_not_position():
    """Reordering the manifest must not change any graph's seed."""
    root = seeds.root(42)
    layout_ss = seeds.keyed(seeds.stage(root, seeds.StageSeed.LAYOUT),
                              "kamada-kawai")
    ids = [f"g_{i:04d}.graphml" for i in range(50)]

    forward = {gid: _per_graph_seed(layout_ss, gid) for gid in ids}
    reverse = {gid: _per_graph_seed(layout_ss, gid) for gid in reversed(ids)}
    interleaved = {gid: _per_graph_seed(layout_ss, gid)
                   for gid in (ids[::2] + ids[1::2])}

    assert forward == reverse == interleaved


def test_per_graph_seed_independent_of_other_graphs():
    """Removing any subset of graph_ids must not change the seed of
    any kept graph_id — i.e. the assignment is a pure function of
    graph_id, not of the manifest's contents."""
    root = seeds.root(7)
    l_ss = seeds.keyed(seeds.stage(root, seeds.StageSeed.LAYOUT), "FMMM")
    full = [f"x_{i}" for i in range(20)]
    seeds_full = {gid: _per_graph_seed(l_ss, gid) for gid in full}

    pruned = [gid for i, gid in enumerate(full) if i % 3 != 0]
    seeds_pruned = {gid: _per_graph_seed(l_ss, gid) for gid in pruned}

    for gid in pruned:
        assert seeds_pruned[gid] == seeds_full[gid]


def test_per_graph_seed_differs_per_layout():
    """Same graph_id under two layouts must get independent seeds."""
    root = seeds.root(1)
    stage_ss = seeds.stage(root, seeds.StageSeed.LAYOUT)
    s1 = _per_graph_seed(seeds.keyed(stage_ss, "fruchterman-reingold"),
                          "g.graphml")
    s2 = _per_graph_seed(seeds.keyed(stage_ss, "stress-majorization"),
                          "g.graphml")
    assert s1 != s2


def test_per_graph_seed_deterministic_across_calls():
    root = seeds.root(99)
    l_ss = seeds.keyed(seeds.stage(root, seeds.StageSeed.LAYOUT), "sfdp")
    a = _per_graph_seed(l_ss, "abc.graphml")
    b = _per_graph_seed(l_ss, "abc.graphml")
    assert a == b


# ---- T2: per-layout seed is layout-name-keyed -------------------------

def test_per_layout_seed_is_name_keyed_not_alphabetical_index():
    """Inserting a new layout into the registry must not change the
    seed of any layout already there."""
    root = seeds.root(2024)
    stage_ss = seeds.stage(root, seeds.StageSeed.LAYOUT)
    canonical = ["arc-bfs", "circular", "FMMM", "fruchterman-reingold",
                 "kamada-kawai", "planar", "random", "spectral"]
    extended = canonical + ["aaa-new-layout", "zzz-another"]
    extended.sort()  # so alphabetical position of every existing entry shifts

    s_canonical = {n: int(seeds.keyed(stage_ss, n).generate_state(1)[0])
                   for n in canonical}
    s_extended = {n: int(seeds.keyed(stage_ss, n).generate_state(1)[0])
                  for n in extended}

    for n in canonical:
        assert s_canonical[n] == s_extended[n], (
            f"layout {n!r} seed perturbed by adding new layouts")


def test_per_layout_seed_distinct_across_layouts():
    root = seeds.root(13)
    stage_ss = seeds.stage(root, seeds.StageSeed.LAYOUT)
    names = ["a", "b", "c", "fruchterman-reingold", "kamada-kawai"]
    seen = {n: int(seeds.keyed(stage_ss, n).generate_state(1)[0])
            for n in names}
    assert len(set(seen.values())) == len(names)


# ---- T3: per-source RNG independence ----------------------------------

def test_per_source_seed_independent_of_other_sources():
    """Adding/removing one source must not change another source's seed."""
    root = seeds.root(55)
    sample_ss = seeds.stage(root, seeds.StageSeed.SAMPLE)

    sources_full = ["rome", "north", "wikipathways", "tudataset"]
    seeds_full = {s: _seed_for_source(sample_ss, s) for s in sources_full}

    sources_pruned = ["rome", "wikipathways"]  # 'north', 'tudataset' removed
    seeds_pruned = {s: _seed_for_source(sample_ss, s) for s in sources_pruned}

    for s in sources_pruned:
        assert seeds_pruned[s] == seeds_full[s]


def test_per_source_seed_differs_per_source():
    root = seeds.root(0)
    sample_ss = seeds.stage(root, seeds.StageSeed.SAMPLE)
    s_a = _seed_for_source(sample_ss, "alpha")
    s_b = _seed_for_source(sample_ss, "beta")
    assert s_a != s_b


def test_per_source_seed_in_uint32_range():
    """RandomState requires a 32-bit seed."""
    root = seeds.root(0)
    sample_ss = seeds.stage(root, seeds.StageSeed.SAMPLE)
    for s in ("rome", "tudataset", "wikipathways", "x", ""):
        v = _seed_for_source(sample_ss, s)
        assert 0 <= v < 2 ** 32


# ---- T3 (end-to-end): sample stage kept set is per-source independent --

def _make_manifest(sources_with_n: dict[str, int]) -> pd.DataFrame:
    """Build a synthetic real_world manifest with controlled sizes.

    Each source gets ``n`` rows whose (n_nodes, density) varies enough
    that ``pd.qcut`` finds quintiles. graph_ids are unique across the
    whole frame so no two rows clash.
    """
    rng = np.random.default_rng(0)
    rows = []
    counter = 0
    for src, n in sources_with_n.items():
        for i in range(n):
            rows.append({
                "graph_id": f"{src}_{i:04d}.graphml",
                "category": "real_world",
                "source": src,
                "n_nodes": int(10 + rng.integers(0, 60)),
                "density": float(rng.random() * 0.4 + 0.05),
            })
            counter += 1
    return pd.DataFrame(rows)


def test_sample_stage_kept_set_per_source_independent(tmp_path,
                                                       monkeypatch):
    """Removing source S must not change the kept set for any other
    source. End-to-end through SampleStage.run, not just the seed
    helper."""
    from dataclasses import replace
    from graph_generation.config import (
        DedupConfig, GenerateConfig, LayoutsConfig, MetricsConfig,
        PipelineConfig, SampleConfig, SourcesConfig, StageConfig,
        ValidateConfig,
    )
    from graph_generation.stages.base import PipelineContext
    from graph_generation.stages.sample import SampleStage

    def make_ctx(out: pd.DataFrame, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        out.to_csv(out_dir / "manifest.csv", index=False)
        cfg = PipelineConfig(
            seed=2024, out_dir=out_dir, parallel_workers=1,
            generate=GenerateConfig(count=0, n_min=2, n_max=10,
                                      generators="*", max_retries=10),
            validate=ValidateConfig(n_min=2, n_max=75, density_cap=1.0,
                                     require_connected=True,
                                     require_simple=True),
            stage=StageConfig(caps={}, default_cap=10000,
                                n_min_real_world=8),
            sample=SampleConfig(enabled=True, seed_offset=0,
                                  caps={"S1": 30, "S2": 30, "S3": 30}),
            dedup=DedupConfig(enabled=False, method="properties"),
            layouts=LayoutsConfig(selected=[], exclude=[]),
            metrics=MetricsConfig(selected="*"),
            sources=SourcesConfig(benchmark=[], real_world=[],
                                    graphs_with_drawings=[]),
        )
        return PipelineContext.from_config(cfg)

    full = _make_manifest({"S1": 100, "S2": 100, "S3": 100})
    pruned = full[full["source"] != "S2"].reset_index(drop=True)

    # The unlink loop in SampleStage.run wants graphml files to exist so
    # it can unlink them. Stub the unlink path away via monkeypatch.
    out_full = tmp_path / "full"
    out_pruned = tmp_path / "pruned"
    ctx_full = make_ctx(full, out_full)
    ctx_pruned = make_ctx(pruned, out_pruned)

    from pathlib import Path as _P
    monkeypatch.setattr("graph_generation.stages.sample.resolve_graph_path",
                          lambda out, row: _P(str(out)) / "missing.graphml")

    SampleStage().run(ctx_full)
    SampleStage().run(ctx_pruned)

    kept_full = pd.read_csv(out_full / "manifest.csv")
    kept_pruned = pd.read_csv(out_pruned / "manifest.csv")

    for src in ("S1", "S3"):
        ids_full = set(kept_full[kept_full["source"] == src]["graph_id"])
        ids_pruned = set(kept_pruned[kept_pruned["source"] == src]["graph_id"])
        assert ids_full == ids_pruned, (
            f"source {src!r} kept-set perturbed by removing S2: "
            f"only_in_full={sorted(ids_full - ids_pruned)[:5]!r}, "
            f"only_in_pruned={sorted(ids_pruned - ids_full)[:5]!r}")


# ---- T7: adding a new layout doesn't perturb existing layouts ---------

def test_adding_layout_does_not_perturb_existing_per_graph_seeds():
    """End-to-end: a new layout in the registry must not change the
    seed assigned to any (existing layout, existing graph) pair."""
    root = seeds.root(2024)
    stage_ss = seeds.stage(root, seeds.StageSeed.LAYOUT)

    canonical_layouts = ["arc-bfs", "FMMM", "fruchterman-reingold",
                          "kamada-kawai", "planar", "random", "sfdp",
                          "spectral", "stress-majorization"]
    graph_ids = [f"g_{i:04d}.graphml" for i in range(20)]

    seeds_canonical = {
        (lyt, gid): _per_graph_seed(seeds.keyed(stage_ss, lyt), gid)
        for lyt in canonical_layouts for gid in graph_ids
    }

    extended = canonical_layouts + ["aaa-new", "zzz-also-new"]
    seeds_extended = {
        (lyt, gid): _per_graph_seed(seeds.keyed(stage_ss, lyt), gid)
        for lyt in extended for gid in graph_ids
    }

    for key in seeds_canonical:
        assert seeds_canonical[key] == seeds_extended[key]
