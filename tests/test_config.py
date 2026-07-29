"""Smoke tests for the pipeline config loader."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from graph_generation.config import load


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "pipeline.toml"


def test_default_config_loads():
    cfg = load(DEFAULT_CONFIG)
    assert cfg.seed == 20260421
    assert cfg.generate.count == 25000
    assert cfg.generate.n_max == 75
    assert cfg.validate.density_cap == "piecewise"
    assert cfg.layouts.exclude == ["twopi"]
    assert cfg.dedup.method == "properties"
    assert cfg.sample.caps["TUDataset/QM9"] == 2500


def test_env_var_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("EFFECTS_OUT", "/tmp/test_out")
    cfg = load(DEFAULT_CONFIG)
    assert str(cfg.out_dir).replace("\\", "/") == "/tmp/test_out"


def test_env_var_default(monkeypatch):
    monkeypatch.delenv("EFFECTS_OUT", raising=False)
    cfg = load(DEFAULT_CONFIG)
    assert cfg.out_dir == Path("./output")


def test_missing_required_field(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("[pipeline]\nseed = 1\n")
    with pytest.raises(ValueError, match="missing required field"):
        load(bad)


def test_seed_cascade_independence():
    from graph_generation.seeds import StageSeed, root, stage, per_unit, rng_from
    s = root(20260421)
    g = stage(s, StageSeed.GENERATE)
    l = stage(s, StageSeed.LAYOUT)
    assert rng_from(g).integers(0, 10**9) != rng_from(l).integers(0, 10**9)
    children = per_unit(g, 5)
    seqs = [rng_from(c).integers(0, 10**9) for c in children]
    assert len(set(seqs)) == 5
