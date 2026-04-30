"""Layout stage - run every selected layout over every manifest row."""

from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import networkx as nx
import numpy as np
import pandas as pd
from tqdm import tqdm

from .. import seeds
from ..layouts import LAYOUT_REGISTRY, Layout, NotApplicable
from ..manifest import resolve_drawing_path, resolve_graph_path
from ..rescale import DIAMETER, standardise
from .base import PipelineContext, Stage
from . import register_stage


def _select_layouts(selected, exclude: List[str]) -> List[Layout]:
    if isinstance(selected, str) and selected == "*":
        names = sorted(LAYOUT_REGISTRY)
    elif isinstance(selected, (list, tuple)):
        names = list(selected)
    else:
        names = [str(selected)]
    excluded = set(exclude or [])
    out: List[Layout] = []
    for name in names:
        if name in excluded:
            continue
        if name not in LAYOUT_REGISTRY:
            print(f"[layout] unknown layout {name!r}; skipping", file=sys.stderr)
            continue
        out.append(LAYOUT_REGISTRY[name])
    return out


_OUTCOME_OK = "ok"
_OUTCOME_SKIPPED_CACHED = "cached"
_OUTCOME_SKIPPED_NA = "not_applicable"
_OUTCOME_FAILED = "failed"


def _per_graph_seed(ss_bytes: bytes, graph_id: str) -> int:
    base_ss = np.random.SeedSequence(list(ss_bytes))
    child = base_ss.spawn(1)[0]
    extra = np.frombuffer(graph_id.encode("utf-8"), dtype=np.uint8)
    if extra.size:
        child = np.random.SeedSequence(
            entropy=int.from_bytes(child.generate_state(1).tobytes(), "big"),
            spawn_key=tuple(int(b) for b in extra[:8]),
        )
    return int(child.generate_state(1)[0])


def _run_one(layout_name: str, graph_path: str, drawing_path: str,
             seed: int, row: Dict) -> Tuple[str, str, Optional[str], float]:
    """Worker - load graph, run layout, write drawing graphml.

    Returns (graph_id, outcome, error_message_or_none, seconds)."""
    graph_id = row["graph_id"]
    layout = LAYOUT_REGISTRY[layout_name]
    out_path = Path(drawing_path)
    if out_path.exists():
        return graph_id, _OUTCOME_SKIPPED_CACHED, None, 0.0

    src = Path(graph_path)
    if not src.exists():
        return graph_id, _OUTCOME_FAILED, f"missing source graph: {src}", 0.0

    try:
        G = nx.read_graphml(src)
    except Exception as e:
        return graph_id, _OUTCOME_FAILED, f"read_graphml: {e}", 0.0

    try:
        if not layout.applies_to(G):
            return graph_id, _OUTCOME_SKIPPED_NA, None, 0.0
    except Exception as e:
        return graph_id, _OUTCOME_FAILED, f"applies_to: {e}", 0.0

    t0 = time.perf_counter()
    try:
        positions, bends = layout.fn(G, seed)
    except NotApplicable:
        return graph_id, _OUTCOME_SKIPPED_NA, None, 0.0
    except Exception as e:
        return graph_id, _OUTCOME_FAILED, f"{type(e).__name__}: {e}", 0.0
    dt = time.perf_counter() - t0

    try:
        positions, bends = standardise(positions, bends or {})
        for nid, xy in positions.items():
            if nid not in G.nodes:
                return (graph_id, _OUTCOME_FAILED,
                        f"unknown node {nid!r}", dt)
            G.nodes[nid]["x"] = float(xy[0])
            G.nodes[nid]["y"] = float(xy[1])
            G.nodes[nid]["width"] = DIAMETER
            G.nodes[nid]["height"] = DIAMETER
        if bends:
            for (u, v), pts in bends.items():
                if G.has_edge(u, v):
                    G.edges[u, v]["bends"] = list(pts)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import geg as _geg
            tmp = out_path.with_suffix(out_path.suffix + ".tmp")
            _geg.write_graphml(G, str(tmp))
            tmp.replace(out_path)
        except ImportError:
            tmp = out_path.with_suffix(out_path.suffix + ".tmp")
            nx.write_graphml(G, tmp)
            tmp.replace(out_path)
    except Exception as e:
        return graph_id, _OUTCOME_FAILED, f"write: {e}", dt

    return graph_id, _OUTCOME_OK, None, dt


@register_stage
class LayoutStage(Stage):
    name = "layout"
    parallel = True
    idempotent = True

    def run(self, ctx: PipelineContext) -> None:
        if not ctx.manifest_path.exists():
            print("[layout] no manifest; nothing to lay out")
            return

        layouts = _select_layouts(ctx.config.layouts.selected,
                                   ctx.config.layouts.exclude)
        if not layouts:
            print("[layout] no layouts selected")
            return

        df = pd.read_csv(ctx.manifest_path, low_memory=False)
        if df.empty:
            print("[layout] manifest is empty")
            return

        df["source"] = df["source"].fillna("").astype(str)
        rows = df.to_dict("records")
        print(f"[layout] graphs={len(rows):,}  layouts={len(layouts)}  "
              f"workers={ctx.config.parallel_workers}")

        layout_ss = seeds.stage(ctx.root_ss, seeds.StageSeed.LAYOUT)
        per_layout_ss = seeds.per_unit(layout_ss, len(layouts))

        summary: Dict[str, Dict[str, int]] = {}
        for layout, l_ss in zip(layouts, per_layout_ss):
            summary[layout.name] = self._run_layout(
                ctx, layout, l_ss, rows,
            )

        print()
        print("[layout] summary")
        print(f"  {'layout':<22s} {'ok':>6s} {'cached':>7s} "
              f"{'n/a':>5s} {'fail':>5s}")
        for name, s in summary.items():
            print(f"  {name:<22s} {s['ok']:>6d} {s['cached']:>7d} "
                  f"{s['na']:>5d} {s['fail']:>5d}")

    def _run_layout(self, ctx: PipelineContext, layout: Layout,
                    layout_ss: np.random.SeedSequence,
                    rows: List[Dict]) -> Dict[str, int]:
        per_graph_ss = seeds.per_unit(layout_ss, len(rows))
        seeds_per_row = [int(s.generate_state(1)[0]) for s in per_graph_ss]

        tasks = []
        for row, sd in zip(rows, seeds_per_row):
            graph_path = resolve_graph_path(ctx.out_dir, row)
            drawing_path = resolve_drawing_path(
                ctx.out_dir, layout.name, row,
            )
            tasks.append((str(graph_path), str(drawing_path), sd, row))

        n_ok = n_cached = n_na = n_fail = 0
        workers = max(1, int(ctx.config.parallel_workers))

        if workers == 1 or layout.backend != "native":
            for graph_path, drawing_path, sd, row in tqdm(
                    tasks, unit="graph", desc=layout.name):
                gid, outcome, err, _ = _run_one(
                    layout.name, graph_path, drawing_path, sd, row,
                )
                if outcome == _OUTCOME_OK:
                    n_ok += 1
                elif outcome == _OUTCOME_SKIPPED_CACHED:
                    n_cached += 1
                elif outcome == _OUTCOME_SKIPPED_NA:
                    n_na += 1
                else:
                    n_fail += 1
                    if err:
                        print(f"\n[{layout.name}] {gid}: {err}",
                              file=sys.stderr)
        else:
            with ProcessPoolExecutor(max_workers=workers) as ex:
                futs = [
                    ex.submit(_run_one, layout.name, gp, dp, sd, row)
                    for gp, dp, sd, row in tasks
                ]
                for fut in tqdm(as_completed(futs), total=len(futs),
                                  unit="graph", desc=layout.name):
                    gid, outcome, err, _ = fut.result()
                    if outcome == _OUTCOME_OK:
                        n_ok += 1
                    elif outcome == _OUTCOME_SKIPPED_CACHED:
                        n_cached += 1
                    elif outcome == _OUTCOME_SKIPPED_NA:
                        n_na += 1
                    else:
                        n_fail += 1
                        if err:
                            print(f"\n[{layout.name}] {gid}: {err}",
                                  file=sys.stderr)

        return {"ok": n_ok, "cached": n_cached, "na": n_na, "fail": n_fail}
