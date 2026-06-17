"""Parametric TUDataset stager — handles every ``TUDataset/<NAME>`` source."""

from __future__ import annotations

import shutil
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

import networkx as nx
from tqdm import tqdm

from .base import Stager, StagedGraph, register_stager


def _download(url: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_size > 0:
        return
    tmp = dst.with_suffix(dst.suffix + ".part")
    print(f"downloading {url}", flush=True)
    with urllib.request.urlopen(url) as r, tmp.open("wb") as f:
        shutil.copyfileobj(r, f, length=1024 * 1024)
    tmp.replace(dst)


def _read_indicator(path: Path) -> Dict[int, int]:
    mapping: Dict[int, int] = {}
    with path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            mapping[idx] = int(line.strip())
    return mapping


def _read_edges(path: Path) -> List[Tuple[int, int]]:
    edges: List[Tuple[int, int]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            a, b = line.split(",")
            edges.append((int(a.strip()), int(b.strip())))
    return edges


def _read_node_xy(path: Path) -> Dict[int, Tuple[float, float]]:
    """Parse cols 0-1 of ``<ds>_node_attributes.txt`` as ``(x, y)``.

    TUDataset's per-node attribute file is comma-separated, one row
    per node in indicator order (1-indexed). For sources where the
    first two columns happen to be 2D coordinates (COIL-DEL is the
    canonical case — image-feature pixel positions), we attach them
    as ``x`` / ``y`` node attrs so the curator drawing survives into
    ``graphs-with-drawings/<source>/``. Sources without coords (or
    with non-coord first columns) just don't pass this helper a path.
    """
    out: Dict[int, Tuple[float, float]] = {}
    with path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            parts = line.split(",")
            if len(parts) < 2:
                continue
            try:
                out[idx] = (float(parts[0].strip()),
                            float(parts[1].strip()))
            except ValueError:
                continue
    return out


def _build_graphs(
    edges: List[Tuple[int, int]],
    node_to_graph: Dict[int, int],
    node_xy: Dict[int, Tuple[float, float]] | None = None,
) -> Dict[int, nx.Graph]:
    by_graph: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
    for u, v in edges:
        g = node_to_graph[u]
        if node_to_graph[v] != g:
            continue
        by_graph[g].append((u, v))

    nodes_by_graph: Dict[int, set[int]] = defaultdict(set)
    for node, g in node_to_graph.items():
        nodes_by_graph[g].add(node)

    out: Dict[int, nx.Graph] = {}
    for g in nodes_by_graph:
        G = nx.Graph()
        if node_xy:
            for n in nodes_by_graph[g]:
                xy = node_xy.get(n)
                if xy is not None:
                    G.add_node(n, x=xy[0], y=xy[1])
                else:
                    G.add_node(n)
        else:
            G.add_nodes_from(nodes_by_graph[g])
        G.add_edges_from(by_graph.get(g, []))
        # Renumber 0..n-1 deterministically while preserving node attrs.
        mapping = {old: i for i, old in enumerate(sorted(G.nodes))}
        H = nx.Graph()
        for old, new in mapping.items():
            H.add_node(new, **dict(G.nodes[old]))
        for u, v in G.edges:
            H.add_edge(mapping[u], mapping[v])
        out[g] = H
    return out


@register_stager
class TUDatasetStager(Stager):
    """One graph per molecule/sample from a TU Dortmund kernel-benchmark set."""

    source_name = "TUDataset/"

    def graphs(self) -> Iterator[StagedGraph]:
        ds = self.source.name.split("/", 1)[1]
        url = self.source.url
        archive_name = self.source.archive_name or f"{ds}.zip"
        archive_path = (self.staging_root / "staging" / "_archives"
                        / "TUDataset" / archive_name)
        extract_workdir = (self.staging_root / "staging"
                           / "_tudataset_extract" / ds)

        _download(url, archive_path)

        if extract_workdir.exists():
            shutil.rmtree(extract_workdir)
        extract_workdir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(extract_workdir)

        inner = extract_workdir / ds
        if not inner.exists():
            subdirs = [p for p in extract_workdir.iterdir() if p.is_dir()]
            if len(subdirs) != 1:
                raise RuntimeError(
                    f"expected one subfolder in {extract_workdir}, got {subdirs}"
                )
            inner = subdirs[0]

        indicator_path = inner / f"{ds}_graph_indicator.txt"
        edges_path = inner / f"{ds}_A.txt"
        if not indicator_path.exists() or not edges_path.exists():
            raise RuntimeError(
                f"missing TUDataset control files in {inner}: "
                f"expected {indicator_path.name} + {edges_path.name}"
            )

        node_to_graph = _read_indicator(indicator_path)
        edges = _read_edges(edges_path)

        # graphs_with_drawings sources (currently just COIL-DEL) ship
        # 2D coordinates in cols 0-1 of node_attributes.txt. Attach
        # them so the curator drawing reaches the manifest cohort
        # downstream. Topology-only sources skip this step.
        node_xy: Dict[int, Tuple[float, float]] | None = None
        if self.source.category == "graphs_with_drawings":
            attrs_path = inner / f"{ds}_node_attributes.txt"
            if attrs_path.exists():
                node_xy = _read_node_xy(attrs_path)
                print(f"  read {len(node_xy):,} (x, y) coords from "
                      f"{attrs_path.name}", flush=True)
            else:
                print(f"  WARN: {ds} is graphs_with_drawings but no "
                      f"{attrs_path.name} — emitting topology-only",
                      flush=True)

        graphs = _build_graphs(edges, node_to_graph, node_xy)

        width = max(4, len(str(max(graphs.keys()))))
        ds_lower = ds.lower()
        for g_id in tqdm(sorted(graphs), unit="graph", desc=f"write {ds}"):
            yield StagedGraph(
                name=f"{ds_lower}_graph{g_id:0{width}d}",
                graph=graphs[g_id],
            )

        shutil.rmtree(extract_workdir, ignore_errors=True)
