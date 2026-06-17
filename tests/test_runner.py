"""Smoke tests for the stage protocol + runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_generation.cli import main as cli_main
from graph_generation.config import load
from graph_generation.stages import STAGE_ORDER, STAGE_REGISTRY, register_stage
from graph_generation.stages.base import PipelineContext, Stage
from graph_generation.stages.runner import Runner, planned_stages, print_plan


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "pipeline.toml"


def test_canonical_stage_order():
    assert STAGE_ORDER == (
        "generate", "stage",
        "sample", "dedup", "layout", "metrics",
    )


def test_run_only_no_stage_clean(tmp_path):
    """Runner should accept an empty `--only` selection cleanly without
    invoking any stage. (Bare run_all is exercised by the slow
    reproducibility test, since the canonical pipeline now has 6 real
    stages registered after the stage→promote merge.)"""
    cfg = load(DEFAULT_CONFIG)
    runner = Runner(cfg)
    runner.run_only([])  # nothing requested → nothing runs


def test_planned_stages_unknown_target_errors():
    with pytest.raises(ValueError, match="unknown stages"):
        planned_stages(["does-not-exist"])


def test_print_plan_runs(capsys):
    print_plan()
    captured = capsys.readouterr()
    assert "no stages registered" in captured.out or "planned pipeline DAG" in captured.out


def test_register_stage_decorator(monkeypatch):
    monkeypatch.setitem(STAGE_REGISTRY, "_test_stage", None)
    monkeypatch.delitem(STAGE_REGISTRY, "_test_stage")

    @register_stage
    class FakeStage(Stage):
        name = "_test_stage"

        def run(self, ctx: PipelineContext) -> None:
            ctx.extras["ran"] = True

    assert "_test_stage" in STAGE_REGISTRY
    cfg = load(DEFAULT_CONFIG)
    runner = Runner(cfg)
    runner.run_only(["_test_stage"])
    assert runner.ctx.extras.get("ran") is True
    STAGE_REGISTRY.pop("_test_stage", None)


def test_cli_rejects_parallel_layouts_below_one(capsys):
    """``--parallel-layouts 0`` (or negative) must fail before any stage
    runs. The runner's serial path is only well-defined for N >= 1, and
    the shell-side auto-cap floors at 1 — anything lower is a config
    bug we want to surface, not silently coerce."""
    rc = cli_main(["run", "--parallel-layouts", "0", "stage"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "--parallel-layouts must be >= 1" in err

    rc = cli_main(["run", "--parallel-layouts", "-3", "stage"])
    assert rc == 2


def test_cli_parallel_layouts_override_replaces_config(monkeypatch, capsys):
    """Passing --parallel-layouts N rewires the config dataclass before
    the Runner starts. Asserts via a stubbed Runner so the test stays
    fast and doesn't actually execute any stage."""
    captured = {}

    class _StubRunner:
        def __init__(self, cfg):
            captured["parallel_layouts"] = cfg.layouts.parallel_layouts

        def run_only(self, targets):
            captured["targets"] = list(targets)

        def run_all(self): pass
        def run_from(self, start): pass

    monkeypatch.setattr("graph_generation.cli.Runner", _StubRunner)
    rc = cli_main(["run", "--parallel-layouts", "5", "--only", "layout"])
    assert rc == 0
    assert captured["parallel_layouts"] == 5
    assert captured["targets"] == ["layout"]


def test_verify_ids_picks_per_source_minimum():
    """_verify_ids should keep the first N graph_ids per (category,
    source-or-generator) deterministically by lex order."""
    from graph_generation.stages.layout import _verify_ids

    # Two real_world sources, one generator family, calibration mix.
    rows = [
        # rome (8 graphs, want first 3)
        *({"graph_id": f"rome_{i:02d}.graphml",
            "category": "benchmark", "source": "rome",
            "generator": "rome"} for i in range(8)),
        # north (2 graphs — fewer than n, all kept)
        {"graph_id": "north_aa.graphml", "category": "benchmark",
         "source": "north", "generator": "north"},
        {"graph_id": "north_bb.graphml", "category": "benchmark",
         "source": "north", "generator": "north"},
        # generated cohort, source="" → group by generator
        *({"graph_id": f"er_n10_s{i}.graphml",
            "category": "generated", "source": "",
            "generator": "er"} for i in range(5)),
        *({"graph_id": f"bba_n10_s{i}.graphml",
            "category": "generated", "source": "",
            "generator": "bba"} for i in range(5)),
    ]
    keep = _verify_ids(rows, n=3)
    # rome: 3 lex-smallest of 8
    assert "rome_00.graphml" in keep
    assert "rome_01.graphml" in keep
    assert "rome_02.graphml" in keep
    assert "rome_03.graphml" not in keep
    # north: both, since n=2 < 3
    assert "north_aa.graphml" in keep
    assert "north_bb.graphml" in keep
    # generated/er: 3 of 5
    assert sum(1 for k in keep if k.startswith("er_")) == 3
    # generated/bba: 3 of 5
    assert sum(1 for k in keep if k.startswith("bba_")) == 3
    # n=0 disables
    assert _verify_ids(rows, n=0) == set()
