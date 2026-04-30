"""Generate stage — produces the ``generated`` and ``calibration`` cohorts.

Three sub-passes (always run in order):

1. ``sampled`` — N graphs from the 12-family generator registry, seeded
   from the GENERATE leg of the cascade (config.generate.count graphs).
2. ``calibration`` — the canonical anchor set (K_n, K_ij, grids, etc.)
   from :func:`graph_generation.calibration.catalogue`.
3. ``exhaustive_small`` — every connected non-iso graph on n ∈ {1..7}
   from NetworkX's Graph Atlas.

All three append to ``out/manifest.csv`` via :class:`ManifestWriter`,
and write graphml files under ``out/graphs/<category>/``. The pass is
idempotent: rows whose ``graph_id`` already exists in the manifest are
skipped, so a re-run only fills in gaps.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Set

import networkx as nx
import numpy as np
import pandas as pd
from tqdm import tqdm

from .. import seeds
from ..calibration import catalogue
from ..manifest import (
    ManifestWriter, graph_filename, graphs_dir, write_graph,
)
from ..properties import compute
from ..sampling import sample_one
from ..subprocess_guard import close_guarded_pool
from .base import PipelineContext, Stage
from . import register_stage


def _existing_graph_ids(manifest_path: Path) -> Set[str]:
    if not manifest_path.exists() or manifest_path.stat().st_size == 0:
        return set()
    return set(pd.read_csv(manifest_path, usecols=["graph_id"])["graph_id"])


@register_stage
class GenerateStage(Stage):
    name = "generate"
    parallel = True
    idempotent = True

    def run(self, ctx: PipelineContext) -> None:
        self._sampled(ctx)
        self._calibration(ctx)
        self._exhaustive_small(ctx)

    def _sampled(self, ctx: PipelineContext) -> None:
        cfg = ctx.config.generate
        out_dir = ctx.out_dir
        gdir = graphs_dir(out_dir, "generated")
        gdir.mkdir(parents=True, exist_ok=True)

        gen_ss = seeds.stage(ctx.root_ss, seeds.StageSeed.GENERATE)
        rng = seeds.rng_from(gen_ss)

        existing = _existing_graph_ids(ctx.manifest_path)
        target = cfg.count
        n_ok = sum(1 for x in existing if x.endswith(".graphml") and "_n" in x
                   and not x.startswith("calibration_") and not x.startswith("exhaustive_"))
        if n_ok >= target:
            print(f"[generate.sampled] manifest already has >= {target} sampled rows; skipping")
            return

        print(f"[generate.sampled] target={target}  resume_from={n_ok}")
        n_failed_samples = 0
        stats: dict = {"tried": {}, "succeeded": {}}

        with ManifestWriter(ctx.manifest_path) as manifest, \
                tqdm(total=target, initial=n_ok, unit="graph") as bar:
            while n_ok < target:
                sampled = sample_one(
                    rng,
                    n_min=cfg.n_min,
                    n_max=cfg.n_max,
                    max_retries=cfg.max_retries,
                    stats=stats,
                )
                if sampled is None:
                    n_failed_samples += 1
                    if n_failed_samples > 100:
                        raise RuntimeError(
                            "100 consecutive sampling failures — aborting"
                        )
                    continue
                n_failed_samples = 0

                G = sampled.graph
                fname = graph_filename(
                    sampled.generator, G.number_of_nodes(),
                    G.number_of_edges(), sampled.seed,
                )
                if fname in existing:
                    continue
                existing.add(fname)

                write_graph(G, gdir / fname)
                manifest.append(
                    graph_id=fname,
                    generator=sampled.generator,
                    category="generated",
                    seed=sampled.seed,
                    params=sampled.params,
                    properties=compute(G),
                )
                n_ok += 1
                bar.update(1)

        close_guarded_pool()
        self._print_yields(stats)

    def _calibration(self, ctx: PipelineContext) -> None:
        out_dir = ctx.out_dir
        gdir = graphs_dir(out_dir, "calibration")
        gdir.mkdir(parents=True, exist_ok=True)
        existing = _existing_graph_ids(ctx.manifest_path)

        entries = catalogue(n_max=ctx.config.generate.n_max)
        print(f"[generate.calibration] entries={len(entries)} "
              f"(n_max={ctx.config.generate.n_max})")
        written = skipped_existing = skipped_disconnected = 0

        with ManifestWriter(ctx.manifest_path) as manifest:
            for name, G in entries:
                if not nx.is_connected(G):
                    skipped_disconnected += 1
                    continue
                fname = (f"calibration_{name}_n{G.number_of_nodes()}"
                         f"_m{G.number_of_edges()}.graphml")
                if fname in existing:
                    skipped_existing += 1
                    continue
                existing.add(fname)
                write_graph(G, gdir / fname)
                manifest.append(
                    graph_id=fname,
                    generator="calibration",
                    category="calibration",
                    seed=0,
                    params={"family": name},
                    properties=compute(G),
                )
                written += 1
        print(f"[generate.calibration] wrote={written} "
              f"skipped_existing={skipped_existing} "
              f"skipped_disconnected={skipped_disconnected}")

    def _exhaustive_small(self, ctx: PipelineContext, n_values: Iterable[int] = (1, 2, 3, 4, 5, 6, 7)) -> None:
        out_dir = ctx.out_dir
        gdir = graphs_dir(out_dir, "calibration")
        gdir.mkdir(parents=True, exist_ok=True)
        existing = _existing_graph_ids(ctx.manifest_path)

        n_set = set(n_values)
        atlas = nx.graph_atlas_g()
        eligible = [
            (idx, G) for idx, G in enumerate(atlas)
            if G.number_of_nodes() in n_set and nx.is_connected(G)
        ]
        print(f"[generate.exhaustive] atlas={len(atlas)} eligible={len(eligible)}")

        written = skipped_existing = 0
        with ManifestWriter(ctx.manifest_path) as manifest:
            for idx, G in tqdm(eligible, unit="graph"):
                n, m = G.number_of_nodes(), G.number_of_edges()
                fname = f"exhaustive_n{n}_atlas{idx:04d}_m{m}.graphml"
                if fname in existing:
                    skipped_existing += 1
                    continue
                existing.add(fname)
                G = nx.convert_node_labels_to_integers(G)
                G.graph.clear()
                for _, attrs in G.nodes(data=True):
                    attrs.clear()
                for _, _, attrs in G.edges(data=True):
                    attrs.clear()
                write_graph(G, gdir / fname)
                manifest.append(
                    graph_id=fname,
                    generator="exhaustive_small",
                    category="calibration",
                    seed=0,
                    params={"atlas_index": idx, "n": n},
                    properties=compute(G),
                )
                written += 1
        print(f"[generate.exhaustive] wrote={written} "
              f"skipped_existing={skipped_existing}")

    @staticmethod
    def _print_yields(stats: dict) -> None:
        tried = stats.get("tried", {})
        succeeded = stats.get("succeeded", {})
        if not tried:
            return
        total_tried = sum(tried.values())
        print("[generate.sampled] per-generator yield (succ/tried):")
        for name in sorted(tried, key=lambda k: -tried[k]):
            t = tried[name]
            s = succeeded.get(name, 0)
            print(f"  {name:15s} {s:>6d} / {t:<6d}  "
                  f"yield={100 * s / t:5.1f}%   share={100 * t / total_tried:5.1f}%")
