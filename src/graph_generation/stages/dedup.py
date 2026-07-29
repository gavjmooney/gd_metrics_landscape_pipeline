"""Dedup stage — cross-source iso/near-iso dedup of the manifest.

Default mode (``method = "properties"``): group rows by the rounded
24-invariant tuple from the manifest and treat each non-singleton
group as one iso class. Strict mode (``method = "wl_vf2"``): WL hash
sub-bucketing then VF2 isomorphism within each property group.

Winner selection is deterministic:
    1. Lowest tier (untouchable: graphs_with_drawings + exhaustive_small;
       named: benchmark / houseofgraphs / netzschleuder; bulk: rest).
    2. Smallest source by current row count (preserves diversity in
       small named sets).
    3. Lexicographic graph_id final tiebreak.

Resume contract — every loser graph_id is written to
``manifest.dedup-audit.csv`` (column ``dropped_graph_id``) before its
graphml is unlinked. The stage and generate stages BOTH read this
sidecar on the next run and treat audited IDs as already-handled, so
re-runs skip the duplicates instead of re-staging them only to have
this stage drop them again. The audit is deterministic across runs
because winner selection is, so a re-run with the same manifest
produces a byte-identical audit.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Set

import networkx as nx
import pandas as pd
from tqdm import tqdm

from ..manifest import resolve_graph_path
from .base import PipelineContext, Stage
from . import register_stage


_TIER_UNTOUCHABLE = 0
_TIER_NAMED = 1
_TIER_BULK = 2


def _read_graph_any(path) -> nx.Graph:
    """Read a staged graph for isomorphism testing, dispatching on extension.

    The ``graphs_with_drawings`` cohort is stored as ``.geg``; every topology
    cohort is ``.graphml``. WL/VF2 only needs topology, but the reader must
    still understand both formats so a ``.geg`` graph isn't silently skipped
    (which would leave a topology duplicate un-deduped against it).
    """
    if str(path).endswith(".geg"):
        import geg
        return geg.read_geg(str(path))
    return nx.read_graphml(path)


def _row_tier(row: dict) -> int:
    if row.get("category") == "graphs_with_drawings":
        return _TIER_UNTOUCHABLE
    if row.get("generator") == "exhaustive_small":
        return _TIER_UNTOUCHABLE
    if row.get("category") == "benchmark":
        return _TIER_NAMED
    src = row.get("source") or ""
    if src == "houseofgraphs" or src.startswith("netzschleuder"):
        return _TIER_NAMED
    return _TIER_BULK


_PROP_COLS = [
    "n_nodes", "n_edges", "density",
    "is_bipartite", "is_planar", "is_tree", "is_forest",
    "is_regular", "is_eulerian",
    "min_degree", "max_degree", "mean_degree", "degree_std",
    "diameter", "radius", "avg_shortest_path_length",
    "n_triangles", "average_clustering", "transitivity",
    "degree_assortativity",
    "n_biconnected_components", "degeneracy",
    "crossing_number_lb_euler", "crossing_number_lb_bipartite",
]


class _UnionFind:
    def __init__(self, items: Iterable[str]):
        self.parent: Dict[str, str] = {x: x for x in items}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: str, y: str) -> None:
        px, py = self.find(x), self.find(y)
        if px != py:
            self.parent[px] = py


def _pre_filter(df: pd.DataFrame) -> Dict[tuple, List[str]]:
    work = df[_PROP_COLS].copy()
    float_cols = work.select_dtypes(include="float").columns
    work[float_cols] = work[float_cols].round(6).fillna(-99999.0)
    work["graph_id"] = df["graph_id"].values
    groups: Dict[tuple, List[str]] = defaultdict(list)
    for tup_and_id in work.itertuples(index=False, name=None):
        tup, gid = tup_and_id[:-1], tup_and_id[-1]
        groups[tup].append(gid)
    return {k: v for k, v in groups.items() if len(v) > 1}


def _winner(rows: List[dict], source_sizes: Dict[str, int]) -> str:
    def key(row):
        return (_row_tier(row),
                source_sizes.get(row.get("source") or "(none)", 1),
                row["graph_id"])
    return min(rows, key=key)["graph_id"]


@register_stage
class DedupStage(Stage):
    name = "dedup"
    parallel = False
    idempotent = True

    def run(self, ctx: PipelineContext) -> None:
        if not ctx.config.dedup.enabled:
            print("[dedup] disabled in config")
            return
        manifest = ctx.manifest_path
        if not manifest.exists():
            print("[dedup] no manifest")
            return

        df = pd.read_csv(manifest, low_memory=False)
        n_before = len(df)
        print(f"[dedup] manifest rows before: {n_before:,}")

        source_sizes = df["source"].fillna("(none)").value_counts().to_dict()
        rows_by_id: Dict[str, dict] = {}
        for _, r in df.iterrows():
            d = r.to_dict()
            if not isinstance(d.get("source"), str):
                d["source"] = ""
            rows_by_id[d["graph_id"]] = d

        collision_groups = _pre_filter(df)
        n_collision_rows = sum(len(v) for v in collision_groups.values())
        print(f"[dedup] collision groups: {len(collision_groups):,}  "
              f"rows in collisions: {n_collision_rows:,}")

        uf = _UnionFind(df["graph_id"].tolist())

        method = ctx.config.dedup.method
        if method == "wl_vf2":
            self._wl_vf2(uf, collision_groups, rows_by_id, ctx)
        elif method == "properties":
            for group in collision_groups.values():
                anchor = group[0]
                for gid in group[1:]:
                    uf.union(anchor, gid)
        else:
            raise ValueError(f"unknown dedup method: {method!r}")

        classes: Dict[str, List[str]] = defaultdict(list)
        for gid in df["graph_id"]:
            classes[uf.find(gid)].append(gid)
        nontrivial = {root: m for root, m in classes.items() if len(m) > 1}
        n_dup_rows = sum(len(m) - 1 for m in nontrivial.values())
        print(f"[dedup] iso classes >1: {len(nontrivial):,}  drop: {n_dup_rows:,}")

        audit_rows: List[Dict] = []
        drop_ids: Set[str] = set()
        for members in nontrivial.values():
            member_rows = [rows_by_id[g] for g in members]
            winner = _winner(member_rows, source_sizes)
            winner_row = rows_by_id[winner]
            for g in members:
                if g == winner:
                    continue
                r = rows_by_id[g]
                if _row_tier(r) == _TIER_UNTOUCHABLE:
                    continue
                drop_ids.add(g)
                same = (r.get("source") == winner_row.get("source"))
                audit_rows.append({
                    "dropped_graph_id": g,
                    "dropped_source": r.get("source"),
                    "dropped_category": r.get("category"),
                    "kept_graph_id": winner,
                    "kept_source": winner_row.get("source"),
                    "kept_category": winner_row.get("category"),
                    "iso_class_size": len(members),
                    "scope": "within-source" if same else "cross-source",
                })

        if not drop_ids:
            print("[dedup] nothing to drop")
            return

        audit_path = manifest.with_name("manifest.dedup-audit.csv")
        pd.DataFrame(audit_rows).to_csv(audit_path, index=False)
        print(f"[dedup] audit -> {audit_path.name} ({len(audit_rows):,} rows)")

        n_unlinked = n_missing = 0
        for gid in tqdm(drop_ids, desc="[dedup] unlink", unit="file"):
            path = resolve_graph_path(ctx.out_dir, rows_by_id[gid])
            if path.exists():
                path.unlink()
                n_unlinked += 1
            else:
                n_missing += 1
        print(f"[dedup] unlinked={n_unlinked:,}  missing={n_missing:,}")

        keep_df = df[~df["graph_id"].isin(drop_ids)].reset_index(drop=True)
        keep_df.to_csv(manifest, index=False)
        print(f"[dedup] manifest rows: {n_before:,} -> {len(keep_df):,}")

    @staticmethod
    def _wl_vf2(uf: _UnionFind, collision_groups: Dict[tuple, List[str]],
                rows_by_id: Dict[str, dict], ctx: PipelineContext) -> None:
        for group in tqdm(collision_groups.values(), unit="group",
                          desc="[dedup] WL+VF2"):
            graphs: Dict[str, nx.Graph] = {}
            for gid in group:
                try:
                    path = resolve_graph_path(ctx.out_dir, rows_by_id[gid])
                    graphs[gid] = _read_graph_any(path)
                except Exception:
                    continue
            if len(graphs) < 2:
                continue
            buckets: Dict[str, List[str]] = defaultdict(list)
            for gid, G in graphs.items():
                buckets[nx.weisfeiler_lehman_graph_hash(G, iterations=5)].append(gid)
            for bucket in buckets.values():
                if len(bucket) < 2:
                    continue
                for i in range(len(bucket)):
                    for j in range(i + 1, len(bucket)):
                        if nx.is_isomorphic(graphs[bucket[i]], graphs[bucket[j]]):
                            uf.union(bucket[i], bucket[j])
