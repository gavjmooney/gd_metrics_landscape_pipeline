"""Promote stage — filter staged graphml into the manifest cohorts.

Walks ``staging/<source>/`` (or ``staging-graphs-with-drawings/<source>/``
for the layout-carrying cohort), applies the cohort filters from
config, copies each survivor into ``graphs/<category>/<source>/``, and
appends one manifest row per accepted graph. Per-source ``README.md``
files capture provenance and the rejection breakdown.

Filter rules come from ``[validate]`` in config (n bounds, density cap,
connected, simple) — no constants in this module.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Counter as CounterT, Dict, List, Optional, Tuple

import networkx as nx
import pandas as pd
from tqdm import tqdm

from .. import sources as sources_mod
from ..config import ValidateConfig
from ..manifest import (
    MANIFEST_HEADER, ManifestWriter, append_rows, graphs_dir,
)
from ..properties import compute
from ..sources import Source
from ..validation import density_cap_for, is_valid
from .base import PipelineContext, Stage
from . import register_stage


# Category-aware minimum n. real_world topology: 8 (graphs n≤7 are
# exhaustively enumerated in the calibration cohort and add no distinct
# regime). graphs_with_drawings and benchmark: keep small curator
# drawings + benchmark community graphs.
_MIN_N_BY_CATEGORY = {
    "real_world": 8,
    "benchmark": 2,
    "graphs_with_drawings": 2,
}


def _read_clean(path: Path, preserve_attrs: bool
                ) -> Tuple[Optional[nx.Graph], str]:
    """Read graphml and coerce to a simple undirected Graph.

    ``preserve_attrs=True`` keeps node/edge attrs (used by
    graphs_with_drawings to carry the curator's x/y/colour/shape/bends).
    """
    try:
        G = nx.read_graphml(path)
    except Exception as e:  # malformed xml, encoding, etc.
        return None, f"load_error:{type(e).__name__}"

    if G.is_directed():
        G = G.to_undirected(as_view=False)
    if G.is_multigraph():
        G = nx.Graph(G)
    sl = list(nx.selfloop_edges(G))
    if sl:
        G.remove_edges_from(sl)

    if not preserve_attrs:
        G.graph.clear()
        for _, attrs in G.nodes(data=True):
            attrs.clear()
        for _, _, attrs in G.edges(data=True):
            attrs.clear()
        G = nx.convert_node_labels_to_integers(G)
        return G, ""

    G.graph.clear()
    mapping = {old: i for i, old in enumerate(sorted(G.nodes, key=str))}
    H = nx.Graph()
    for old, new in mapping.items():
        attrs = dict(G.nodes[old])
        H.add_node(new, orig_id=str(old), **attrs)
    for u, v, data in G.edges(data=True):
        H.add_edge(mapping[u], mapping[v], **data)
    return H, ""


def _classify(G: nx.Graph, vc: ValidateConfig, category: str
              ) -> Tuple[bool, str]:
    n = G.number_of_nodes()
    min_n = max(_MIN_N_BY_CATEGORY.get(category, vc.n_min), vc.n_min)
    if n < min_n:
        return False, "too_small"
    if vc.n_max and n > vc.n_max:
        return False, "too_large"
    if G.number_of_edges() == 0:
        return False, "no_edges"
    if vc.require_connected and not nx.is_connected(G):
        return False, "disconnected"
    cap = density_cap_for(n, vc.density_cap)
    d = nx.density(G)
    if d > cap:
        return False, f"over_density_cap(n={n},d={d:.3f},cap={cap:.2f})"
    return True, ""


def _staging_dir(out_dir: Path, src: Source) -> Path:
    if src.staging_path:
        return out_dir / src.staging_path
    if src.category == "graphs_with_drawings":
        return out_dir / "staging-graphs-with-drawings" / src.name
    return out_dir / "staging" / src.name


def _target_graph_id(source: str, original_path: Path) -> str:
    safe_source = source.replace("/", "_")
    return f"{safe_source}_{original_path.stem}.graphml"


def _write_graphml(G: nx.Graph, path: Path, preserve_attrs: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if preserve_attrs:
        import geg as _geg
        _geg.write_graphml(G, str(path))
    else:
        nx.write_graphml(G, path)


def _promote_one(
    source_name: str,
    out_dir_str: str,
    existing_ids: set[str],
    vc: ValidateConfig,
) -> Tuple[str, int, int, int, Dict[str, int], List[Dict]]:
    """Worker — promote one source. Returns the per-source stats and the
    rows to append to the manifest (parent merges them under the lock)."""
    out_dir = Path(out_dir_str)
    src = sources_mod.get(source_name)
    category = src.category
    preserve_attrs = category == "graphs_with_drawings"
    staging = _staging_dir(out_dir, src)
    if not staging.exists():
        return source_name, 0, 0, 0, {"missing_staging": 1}, []

    dst = graphs_dir(out_dir, category, src.name)
    dst.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in staging.rglob("*.graphml") if p.is_file())

    accepted = skipped_existing = 0
    reasons: CounterT[str] = Counter()
    rows: List[Dict] = []

    for path in files:
        G, load_err = _read_clean(path, preserve_attrs=preserve_attrs)
        if G is None:
            reasons[load_err] += 1
            continue
        ok, reason = _classify(G, vc, category)
        if not ok:
            reasons[reason.split("(")[0]] += 1
            continue
        graph_id = _target_graph_id(src.name, path)
        if graph_id in existing_ids:
            skipped_existing += 1
            continue
        _write_graphml(G, dst / graph_id, preserve_attrs)
        props = compute(G)
        rows.append({
            "graph_id": graph_id,
            "generator": src.name,
            "category": category,
            "source": src.name,
            "seed": 0,
            "params_json": _json_compact({"staged_from": path.name}),
            **props,
        })
        accepted += 1

    _write_readme(src, dst, staging, len(files), accepted, sum(reasons.values()),
                  skipped_existing, reasons)
    return source_name, len(files), accepted, skipped_existing, dict(reasons), rows


def _json_compact(d: Dict) -> str:
    import json
    return json.dumps(d, separators=(",", ":"), sort_keys=True)


def _write_readme(meta: Source, dst: Path, staging: Path,
                   staged: int, accepted: int, rejected: int,
                   skipped_existing: int, reasons: CounterT[str]) -> None:
    effective = accepted + skipped_existing
    pct = lambda x: 100.0 * x / staged if staged else 0.0
    lines = [
        f"# {meta.name} ({meta.category})",
        "",
        "## Description",
        "",
        meta.description.strip(),
        "",
        "## Citation",
        "",
        meta.citation.strip() if meta.citation else "_No formal citation._",
        "",
    ]
    if meta.url:
        lines += [
            "## Source",
            "",
            f"- Download URL: {meta.url}",
            f"- Archive: `{meta.archive_name}`" if meta.archive_name else "",
            f"- Staging path: `{staging.name}/`",
            "",
        ]
    lines += [
        "## Filters applied",
        "",
        "1. **Coerce undirected** — DiGraphs are `G.to_undirected()`-ed.",
        "2. **Simplify** — multi-edges collapsed, self-loops stripped.",
        "3. **Size** — n bounds from `[validate]` config.",
        "4. **Connected** — disconnected graphs are rejected outright.",
        "5. **Density cap** — `density(G) ≤ density_cap_for(n, mode)` from config.",
        "",
        "## Promotion summary",
        "",
        f"- Generated: {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}",
        f"- Staged files scanned: **{staged}**",
        f"- In manifest after this run: **{effective}** ({pct(effective):.1f}% retained)",
        f"  - newly accepted this run: {accepted}",
        f"  - already promoted in a prior run: {skipped_existing}",
        f"- Rejected by filters: **{rejected}** ({pct(rejected):.1f}% lost)",
    ]
    if reasons:
        lines += ["", "### Rejection breakdown", "",
                  "| Reason | Count | % of staged |", "|---|---|---|"]
        for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
            lines.append(f"| `{reason}` | {count} | {pct(count):.2f}% |")
    sidecar = staging / "PER_GRAPH_CITATIONS.md"
    if sidecar.exists():
        lines += ["", "## Per-graph citations", ""]
        for raw in sidecar.read_text(encoding="utf-8").splitlines():
            if raw.startswith("# "):
                continue
            lines.append(raw)
    lines += ["", "---",
              "_Auto-generated by `pipeline run promote`. Re-running refreshes._",
              ""]
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "README.md").write_text("\n".join(l for l in lines if l != ""), encoding="utf-8")


def _resolve_sources(ctx: PipelineContext) -> List[Source]:
    cfg = ctx.config.sources
    by_cat = {"benchmark": cfg.benchmark, "real_world": cfg.real_world,
              "graphs_with_drawings": cfg.graphs_with_drawings}
    selected: List[Source] = []
    for src in sources_mod.SOURCES.values():
        rule = by_cat.get(src.category)
        if rule is None:
            continue
        if rule == "*" or (isinstance(rule, list) and src.name in rule):
            selected.append(src)
    return selected


def _existing_ids(manifest_path: Path) -> set[str]:
    if not manifest_path.exists() or manifest_path.stat().st_size == 0:
        return set()
    return set(pd.read_csv(manifest_path, usecols=["graph_id"])["graph_id"])


@register_stage
class PromoteStage(Stage):
    name = "promote"
    parallel = True  # per-source workers, but manifest writes are serial
    idempotent = True

    def run(self, ctx: PipelineContext) -> None:
        sources = _resolve_sources(ctx)
        if not sources:
            print("[promote] no sources selected; nothing to do")
            return

        existing_ids = _existing_ids(ctx.manifest_path)
        workers = max(1, ctx.config.parallel_workers)
        vc = ctx.config.validate
        print(f"[promote] {len(sources)} sources × {workers} workers")

        results: List[tuple] = []
        if workers == 1 or len(sources) == 1:
            for s in sources:
                results.append(_promote_one(s.name, str(ctx.out_dir),
                                            existing_ids, vc))
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_promote_one, s.name, str(ctx.out_dir),
                                        set(existing_ids), vc) for s in sources]
                for fut in as_completed(futures):
                    results.append(fut.result())

        # Serial manifest append: gather every row across workers and
        # write under the module-level lock in one batch.
        all_rows: List[Dict] = []
        for source_name, staged, accepted, skipped, reasons, rows in results:
            print(f"[promote]   {source_name:30s} staged={staged:6d}  "
                  f"accepted={accepted:6d}  skipped={skipped:6d}  "
                  f"rejected={sum(reasons.values()):6d}")
            all_rows.extend(rows)
        if all_rows:
            n = append_rows(ctx.manifest_path, all_rows)
            print(f"[promote] appended {n} manifest rows")
