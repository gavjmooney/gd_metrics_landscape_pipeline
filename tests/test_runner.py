"""Smoke tests for the stage protocol + runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_generation.config import load
from graph_generation.stages import STAGE_ORDER, STAGE_REGISTRY, register_stage
from graph_generation.stages.base import PipelineContext, Stage
from graph_generation.stages.runner import Runner, planned_stages, print_plan


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "pipeline.toml"


def test_canonical_stage_order():
    assert STAGE_ORDER == (
        "generate", "stage", "promote",
        "sample", "dedup", "layout", "metrics",
    )


def test_empty_run_clean(monkeypatch, capsys):
    cfg = load(DEFAULT_CONFIG)
    Runner(cfg).run_all()
    captured = capsys.readouterr()
    assert captured.err == ""


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
