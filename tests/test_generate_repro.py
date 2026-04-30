"""Phase-3 self-check: deterministic generation.

Regenerate a small corpus twice with the same seed; the manifest rows
must be byte-identical excluding the wall-clock ``generated_at_utc``
column (timestamps are necessarily different between runs and aren't
part of the deterministic contract).
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from graph_generation.config import load
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
        scrubbed_header = [c for i, c in enumerate(header) if i != ts_idx]
        h.update(",".join(scrubbed_header).encode() + b"\n")
        for row in sorted(reader):
            scrubbed = [c for i, c in enumerate(row) if i != ts_idx]
            h.update(",".join(scrubbed).encode() + b"\n")
    return h.hexdigest()


def _run_small(out_dir: Path, count: int = 100, seed: int = 12345) -> None:
    cfg = load(DEFAULT_CONFIG)
    gen = replace(cfg.generate, count=count, n_min=10, n_max=15, max_retries=20)
    cfg = replace(cfg, seed=seed, out_dir=out_dir, generate=gen)
    runner = Runner(cfg)
    runner.run_only(["generate"])


@pytest.mark.slow
def test_generate_byte_identical(tmp_path):
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"
    _run_small(out_a)
    _run_small(out_b)
    h_a = _hash_manifest(out_a / "manifest.csv")
    h_b = _hash_manifest(out_b / "manifest.csv")
    assert h_a == h_b, (
        f"manifest hashes differ:\n  run_a: {h_a}\n  run_b: {h_b}"
    )
