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


def _build_graphs(
    edges: List[Tuple[int, int]],
    node_to_graph: Dict[int, int],
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
        G.add_nodes_from(nodes_by_graph[g])
        G.add_edges_from(by_graph.get(g, []))
        G = nx.convert_node_labels_to_integers(G)
        G.graph.clear()
        for _, attrs in G.nodes(data=True):
            attrs.clear()
        for _, _, attrs in G.edges(data=True):
            attrs.clear()
        out[g] = G
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
        graphs = _build_graphs(edges, node_to_graph)

        width = max(4, len(str(max(graphs.keys()))))
        ds_lower = ds.lower()
        for g_id in tqdm(sorted(graphs), unit="graph", desc=f"write {ds}"):
            yield StagedGraph(
                name=f"{ds_lower}_graph{g_id:0{width}d}",
                graph=graphs[g_id],
            )

        shutil.rmtree(extract_workdir, ignore_errors=True)
