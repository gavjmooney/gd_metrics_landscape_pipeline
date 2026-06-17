"""Pipeline runner — orchestrate stages from config."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Iterable, List, Sequence

from .._log import fmt_dur, stopwatch
from ..config import PipelineConfig
from . import STAGE_ORDER, STAGE_REGISTRY
from .base import PipelineContext, Stage


def discover_stages() -> None:
    """Import every submodule of :mod:`graph_generation.stages` so each
    ``@register_stage`` decorator runs and the registry fills."""
    pkg = importlib.import_module("graph_generation.stages")
    for m in pkgutil.iter_modules(pkg.__path__):
        if m.name in {"base", "runner"}:
            continue
        importlib.import_module(f"graph_generation.stages.{m.name}")


def planned_stages(targets: Sequence[str] | None = None) -> List[str]:
    """Return the names of stages that will run, in canonical order.

    Stages in :data:`STAGE_ORDER` come first in that order; any extra
    registered stages (e.g. ad-hoc experimental ones) trail at the end
    in registration order.
    """
    discover_stages()
    canonical = [n for n in STAGE_ORDER if n in STAGE_REGISTRY]
    extras = [n for n in STAGE_REGISTRY if n not in STAGE_ORDER]
    full_order = canonical + extras
    if targets is None:
        return full_order
    if isinstance(targets, str):
        targets = [targets]
    requested = set(targets)
    unknown = requested - set(STAGE_REGISTRY) - set(STAGE_ORDER)
    if unknown:
        raise ValueError(f"unknown stages: {sorted(unknown)}")
    return [n for n in full_order if n in requested]


class Runner:
    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg
        self.ctx = PipelineContext.from_config(cfg)

    def _run_sequence(self, names: Sequence[str]) -> None:
        """Run each stage and report per-stage + total wall time."""
        per_stage: list[tuple[str, float]] = []
        with stopwatch() as total:
            for name in names:
                with stopwatch() as elapsed:
                    self._run_one(name)
                per_stage.append((name, elapsed()))
                print(f"[{name}] done in {fmt_dur(elapsed())}", flush=True)
        if len(names) > 1:
            print()
            print("[pipeline] timing summary")
            for n, dt in per_stage:
                print(f"  {n:<10s}  {fmt_dur(dt)}")
            print(f"  {'TOTAL':<10s}  {fmt_dur(total())}")

    def run_all(self) -> None:
        self._run_sequence(planned_stages())

    def run_only(self, targets: Sequence[str]) -> None:
        self._run_sequence(planned_stages(targets))

    def run_from(self, start: str) -> None:
        if start not in STAGE_ORDER:
            raise ValueError(f"unknown stage: {start!r}")
        i = STAGE_ORDER.index(start)
        names = [n for n in planned_stages()
                 if STAGE_ORDER.index(n) >= i]
        self._run_sequence(names)

    def _run_one(self, name: str) -> None:
        cls = STAGE_REGISTRY[name]
        stage: Stage = cls()
        print(f"[{name}] starting", flush=True)
        stage.run(self.ctx)


def print_plan(targets: Sequence[str] | None = None) -> None:
    """Print the stages that would run for the given targets."""
    plan = planned_stages(targets)
    if not plan:
        print("(no stages registered)")
        return
    print("planned pipeline DAG:")
    for n in plan:
        cls = STAGE_REGISTRY[n]
        flags = []
        if getattr(cls, "parallel", False):
            flags.append("parallel")
        if not getattr(cls, "idempotent", True):
            flags.append("non-idempotent")
        suffix = f" [{', '.join(flags)}]" if flags else ""
        print(f"  {n}{suffix}")
