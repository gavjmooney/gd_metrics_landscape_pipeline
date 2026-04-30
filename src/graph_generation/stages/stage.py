"""Stage stage — downloads + writes graphml into ``staging/<source>/``.

Each source's ``Stager`` subclass owns the format-specific parse logic.
The framework selects sources from config (``[sources]``: ``benchmark``,
``real_world``, ``graphs_with_drawings``) and dispatches per-source
work in parallel.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, List

from ..sources import SOURCES, Source
from ..stagers import discover_stagers, stager_for, STAGER_REGISTRY
from .base import PipelineContext, Stage
from . import register_stage


def _resolve_sources(ctx: PipelineContext) -> List[Source]:
    cfg = ctx.config.sources
    selected: List[Source] = []
    by_cat = {"benchmark": cfg.benchmark, "real_world": cfg.real_world,
              "graphs_with_drawings": cfg.graphs_with_drawings}
    for src in SOURCES.values():
        rule = by_cat.get(src.category)
        if rule is None:
            continue
        if rule == "*" or (isinstance(rule, list) and src.name in rule):
            selected.append(src)
    return selected


def _stage_one(source_name: str, staging_root_str: str) -> tuple[str, int, str]:
    """Worker — runs in a child process. Returns (name, count, error)."""
    discover_stagers()
    src = SOURCES[source_name]
    try:
        stager = stager_for(src, Path(staging_root_str))
        n = stager.stage()
        return (source_name, n, "")
    except Exception as e:  # noqa: BLE001 — surface to parent
        return (source_name, 0, f"{type(e).__name__}: {e}")


@register_stage
class StageStage(Stage):
    name = "stage"
    parallel = True
    idempotent = True

    def run(self, ctx: PipelineContext) -> None:
        discover_stagers()
        sources = _resolve_sources(ctx)
        if not sources:
            print("[stage] no sources selected; nothing to do")
            return

        unsupported = [s.name for s in sources
                       if s.name not in STAGER_REGISTRY
                       and not any(s.name.startswith(k)
                                   for k in STAGER_REGISTRY if k.endswith("/"))]
        if unsupported:
            print(f"[stage] WARN: {len(unsupported)} sources have no stager: "
                  f"{unsupported[:6]}{'...' if len(unsupported) > 6 else ''}")
            sources = [s for s in sources if s.name not in unsupported]

        workers = max(1, ctx.config.parallel_workers)
        print(f"[stage] running {len(sources)} stagers across "
              f"{workers} workers")

        if workers == 1 or len(sources) == 1:
            for s in sources:
                name, n, err = _stage_one(s.name, str(ctx.out_dir))
                self._report(name, n, err)
            return

        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_stage_one, s.name, str(ctx.out_dir)): s.name
                       for s in sources}
            for fut in as_completed(futures):
                name, n, err = fut.result()
                self._report(name, n, err)

    @staticmethod
    def _report(name: str, n: int, err: str) -> None:
        if err:
            print(f"[stage]   FAIL  {name}: {err}")
        else:
            print(f"[stage]   {name}: {n} graphs")
