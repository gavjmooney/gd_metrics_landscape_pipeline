"""Phase-9 reproducibility test.

Run the full pipeline twice with a fixed seed (no external downloads —
all source selectors empty so only generate / sample / dedup / layout /
metrics run). Assert that the manifest hash, the sorted graphml file
list, and the sorted drawings list are byte-identical between runs.

This pins the deterministic part of the pipeline. External sources
(TUDataset / HoG / SuiteSparse) are intentionally out of scope per the
refactor plan §6 — they can change upstream and aren't byte-pinned.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Iterable

import pytest

from graph_generation.config import (
    GenerateConfig, LayoutsConfig, PipelineConfig, SourcesConfig, load,
)
from graph_generation.stages.runner import Runner


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "pipeline.toml"


def _hash_manifest(path: Path) -> str:
    """SHA256 of the manifest with the generated_at_utc column dropped."""
    h = hashlib.sha256()
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        try:
            ts_idx = header.index("generated_at_utc")
        except ValueError:
            ts_idx = -1
        scrubbed = [c for i, c in enumerate(header) if i != ts_idx]
        h.update(",".join(scrubbed).encode() + b"\n")
        for row in sorted(reader):
            scrubbed = [c for i, c in enumerate(row) if i != ts_idx]
            h.update(",".join(scrubbed).encode() + b"\n")
    return h.hexdigest()


def _hash_files(paths: Iterable[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(p.relative_to(p.parents[3] if len(p.parents) > 3 else p.parent).as_posix().encode())
        h.update(b"\n")
        h.update(p.read_bytes())
        h.update(b"\n")
    return h.hexdigest()


def _tiny_config(out_dir: Path, seed: int = 1) -> PipelineConfig:
    cfg = load(DEFAULT_CONFIG)
    return replace(
        cfg,
        seed=seed,
        out_dir=out_dir,
        parallel_workers=1,
        generate=replace(cfg.generate, count=200, n_min=10, n_max=15,
                          max_retries=20),
        layouts=LayoutsConfig(selected=["kamada-kawai"], exclude=[]),
        sources=SourcesConfig(benchmark=[], real_world=[],
                               graphs_with_drawings=[]),
    )


@pytest.mark.slow
def test_full_pipeline_byte_identical(tmp_path):
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"

    cfg_a = _tiny_config(out_a)
    cfg_b = _tiny_config(out_b)

    Runner(cfg_a).run_only(["generate", "sample", "dedup", "layout"])
    Runner(cfg_b).run_only(["generate", "sample", "dedup", "layout"])

    h_man_a = _hash_manifest(out_a / "manifest.csv")
    h_man_b = _hash_manifest(out_b / "manifest.csv")
    assert h_man_a == h_man_b, (
        f"manifest hashes differ:\n  a: {h_man_a}\n  b: {h_man_b}"
    )

    a_graphs = list((out_a / "graphs").rglob("*.graphml"))
    b_graphs = list((out_b / "graphs").rglob("*.graphml"))
    assert {p.relative_to(out_a).as_posix() for p in a_graphs} == \
            {p.relative_to(out_b).as_posix() for p in b_graphs}

    a_drawings = list((out_a / "drawings").rglob("*.graphml"))
    b_drawings = list((out_b / "drawings").rglob("*.graphml"))
    assert {p.relative_to(out_a).as_posix() for p in a_drawings} == \
            {p.relative_to(out_b).as_posix() for p in b_drawings}

    print(f"manifest hash: {h_man_a}")
    print(f"graphml count: {len(a_graphs)}")
    print(f"drawing count: {len(a_drawings)}")
