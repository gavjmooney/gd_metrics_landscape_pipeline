"""Sample stage — stratified down-sampling of capped real_world sources.

Untouched cohorts (always kept whole): generated, calibration, benchmark,
graphs_with_drawings. Real-world sources with a cap in
``[sample.caps]`` are stratified by (n_nodes, density) quintile and
sampled proportionally with floor=1 per non-empty cell.

Deterministic via the seed cascade — uses ``StageSeed.SAMPLE`` plus
``[sample].seed_offset`` so a refactor of the offset doesn't perturb
the generated cohort.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from tqdm import tqdm

from .. import seeds
from ..manifest import resolve_graph_path
from .base import PipelineContext, Stage
from . import register_stage


_N_QUANTILE_BINS = 5  # 5 × 5 = 25 strata max


def _stratify(src_df: pd.DataFrame) -> pd.Series:
    n_bin = pd.qcut(src_df["n_nodes"], q=_N_QUANTILE_BINS,
                     labels=False, duplicates="drop")
    d_bin = pd.qcut(src_df["density"], q=_N_QUANTILE_BINS,
                     labels=False, duplicates="drop")
    return n_bin.astype("Int64").astype(str) + "_" + \
           d_bin.astype("Int64").astype(str)


def _allocate(counts: pd.Series, cap: int) -> pd.Series:
    raw = (counts * cap / counts.sum()).round().astype(int)
    alloc = raw.clip(lower=1).copy()
    alloc = pd.Series(np.minimum(alloc.values, counts.values),
                       index=alloc.index)
    while alloc.sum() > cap:
        over = alloc - raw
        candidates = over[(alloc > 1)].sort_values(ascending=False)
        biggest = candidates.index[0] if not candidates.empty else alloc.idxmax()
        alloc[biggest] -= 1
    while alloc.sum() < cap:
        headroom = counts - alloc
        candidates = headroom[headroom > 0]
        if candidates.empty:
            break
        alloc[candidates.idxmax()] += 1
    return alloc


def _sample_one_source(src_df: pd.DataFrame, cap: int,
                        rng: np.random.RandomState) -> pd.DataFrame:
    if len(src_df) <= cap:
        return src_df.copy()
    work = src_df.copy()
    work["_stratum"] = _stratify(work)
    counts = work.groupby("_stratum").size()
    alloc = _allocate(counts, cap)
    keepers = []
    for stratum, n in alloc.items():
        sub = work[work["_stratum"] == stratum]
        n = min(int(n), len(sub))
        if n <= 0:
            continue
        keepers.append(sub.sample(n=n, random_state=rng))
    return pd.concat(keepers).drop(columns=["_stratum"])


def _seed_for(ctx: PipelineContext) -> int:
    """Derive the RandomState seed from the cascade. RandomState wants
    a 32-bit int; SeedSequence.generate_state(1) gives us one."""
    sample_ss = seeds.stage(ctx.root_ss, seeds.StageSeed.SAMPLE)
    offset = ctx.config.sample.seed_offset
    if offset:
        sample_ss = sample_ss.spawn(offset + 1)[offset]
    return int(sample_ss.generate_state(1)[0])


@register_stage
class SampleStage(Stage):
    name = "sample"
    parallel = False  # touches the manifest serially
    idempotent = True

    def run(self, ctx: PipelineContext) -> None:
        if not ctx.config.sample.enabled:
            print("[sample] disabled in config")
            return
        caps: Dict[str, int] = dict(ctx.config.sample.caps)
        manifest = ctx.manifest_path
        if not manifest.exists():
            print("[sample] no manifest yet; nothing to sample")
            return

        df = pd.read_csv(manifest, low_memory=False)
        n_before = len(df)
        print(f"[sample] manifest rows before: {n_before:,}")

        untouched = df[df["category"].isin(
            ["graphs_with_drawings", "benchmark", "calibration", "generated"])]
        rw = df[df["category"] == "real_world"]

        rng = np.random.RandomState(_seed_for(ctx))
        kept_parts: List[pd.DataFrame] = []
        audit_rows: List[Dict] = []
        for src, group in rw.groupby("source"):
            cap = caps.get(src)
            if cap is None or len(group) <= cap:
                kept_parts.append(group)
                continue
            sampled = _sample_one_source(group, cap, rng)
            kept_parts.append(sampled)
            dropped_ids = set(group["graph_id"]) - set(sampled["graph_id"])
            for _, r in group[group["graph_id"].isin(dropped_ids)].iterrows():
                audit_rows.append({
                    "dropped_graph_id": r["graph_id"],
                    "source": src,
                    "n_nodes": r["n_nodes"],
                    "density": r["density"],
                })

        kept_rw = pd.concat(kept_parts) if kept_parts else rw.iloc[0:0]
        keep_df = pd.concat([untouched, kept_rw]).reset_index(drop=True)
        n_after = len(keep_df)
        n_dropped = n_before - n_after
        print(f"[sample] kept {n_after:,}  dropped {n_dropped:,}")

        if n_dropped == 0:
            return

        audit_path = manifest.with_name("manifest.sampling-audit.csv")
        pd.DataFrame(audit_rows).to_csv(audit_path, index=False)
        print(f"[sample] audit -> {audit_path.name} ({len(audit_rows):,} rows)")

        drop_set = set(df["graph_id"]) - set(keep_df["graph_id"])
        drop_rows = df[df["graph_id"].isin(drop_set)]
        n_unlinked = n_missing = 0
        for _, r in tqdm(drop_rows.iterrows(), total=len(drop_rows),
                          desc="[sample] unlink", unit="file"):
            d = r.to_dict()
            if not isinstance(d.get("source"), str):
                d["source"] = ""
            path = resolve_graph_path(ctx.out_dir, d)
            if path.exists():
                path.unlink()
                n_unlinked += 1
            else:
                n_missing += 1
        print(f"[sample] unlinked={n_unlinked:,}  missing={n_missing:,}")

        keep_df.to_csv(manifest, index=False)
        print(f"[sample] manifest rows: {n_before:,} -> {n_after:,}")
