"""GD-conference drawings collection — convert pre-staged ``.geg`` to GraphML."""

from __future__ import annotations

from typing import Iterator

import networkx as nx
from tqdm import tqdm

import geg

from .base import Stager, StagedGraph, register_stager


def _read_geg(path) -> nx.Graph | None:
    """Load a .geg drawing as a simple undirected Graph keeping x/y/etc."""
    try:
        G = geg.read_geg(str(path))
    except Exception as e:
        print(f"  skip {path.name}: load_error:{type(e).__name__}: {e}")
        return None

    if G.is_directed():
        G = G.to_undirected(as_view=False)
    if G.is_multigraph():
        G = nx.Graph(G)
    G.remove_edges_from(nx.selfloop_edges(G))
    G.graph.clear()

    mapping = {old: i for i, old in enumerate(sorted(G.nodes, key=str))}
    H = nx.Graph()
    for old, new in mapping.items():
        H.add_node(new, orig_id=str(old), **dict(G.nodes[old]))
    for u, v, data in G.edges(data=True):
        H.add_edge(mapping[u], mapping[v], **data)
    return H


@register_stager
class GDCollectionStager(Stager):
    """Walk pre-staged ``.geg`` files (GD00..GD17) and yield each as a graph."""

    source_name = "gd_collection_v1"

    def graphs(self) -> Iterator[StagedGraph]:
        staging_root = self.staging_dir()
        files = sorted(staging_root.rglob("*.geg"))
        print(f"staged .geg files under {staging_root}: {len(files)}")
        for path in tqdm(files, unit="graph", desc=self.source_name):
            year = path.parent.name  # "GD00" .. "GD17"
            G = _read_geg(path)
            if G is None:
                continue
            yield StagedGraph(name=f"gd_{year.lower()}_{path.stem}", graph=G)
