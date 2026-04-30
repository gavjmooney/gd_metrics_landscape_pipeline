"""House of Graphs — Ghent University curated topology-only database."""

from __future__ import annotations

import time
from typing import Iterator, Optional

import networkx as nx
import requests
from tqdm import tqdm

from ..validation import density_cap
from .base import Stager, StagedGraph, register_stager

API_BASE = "https://houseofgraphs.org/api"
LIST_PAGE_SIZE = 200
MIN_N = 8  # real_world cohort: small graphs covered by generator/calibration
MAX_N = 75
REQUEST_DELAY_S = 0.05


def _list_all_ids(session: requests.Session,
                  stop_at: Optional[int] = None) -> list[int]:
    url = f"{API_BASE}/graphs"
    r = session.get(url, params={"page": 0, "size": LIST_PAGE_SIZE},
                    timeout=20)
    r.raise_for_status()
    data = r.json()
    total_pages = data["page"]["totalPages"]
    total_elements = data["page"]["totalElements"]
    ids: list[int] = list(data["_embedded"]["integerList"])
    print(f"HoG /api/graphs: {total_elements:,} graphs across "
          f"{total_pages} pages", flush=True)
    if stop_at is not None and len(ids) >= stop_at:
        return ids[:stop_at]
    for page in tqdm(range(1, total_pages), desc="enumerate IDs", unit="page"):
        r = session.get(url, params={"page": page, "size": LIST_PAGE_SIZE},
                        timeout=20)
        r.raise_for_status()
        ids.extend(r.json()["_embedded"]["integerList"])
        if stop_at is not None and len(ids) >= stop_at:
            return ids[:stop_at]
        time.sleep(REQUEST_DELAY_S)
    return ids


def _fetch_graph(session: requests.Session, gid: int) -> Optional[nx.Graph]:
    try:
        r = session.get(f"{API_BASE}/graphs/{gid}", timeout=15)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    adj = data.get("adjacencyList")
    if not adj:
        return None
    n = len(adj)
    G = nx.Graph()
    G.add_nodes_from(range(n))
    for u, neighbours in enumerate(adj):
        for v in neighbours:
            if v > u:
                G.add_edge(u, v)
    G.remove_edges_from(nx.selfloop_edges(G))
    entity = data.get("entity") or {}
    if entity.get("graphName"):
        G.graph["name"] = str(entity["graphName"])
    if entity.get("canonicalForm"):
        G.graph["canonical_form"] = str(entity["canonicalForm"])
    G.graph["hog_id"] = int(gid)
    return G


def _passes_filter(G: nx.Graph) -> bool:
    n = G.number_of_nodes()
    if n < MIN_N or n > MAX_N:
        return False
    if G.number_of_edges() == 0:
        return False
    if not nx.is_connected(G):
        return False
    if nx.density(G) > density_cap(n):
        return False
    return True


@register_stager
class HouseOfGraphsStager(Stager):
    """Pre-filtered HoG graphs: 8 <= n <= 75, connected, density-capped."""

    source_name = "houseofgraphs"

    def graphs(self) -> Iterator[StagedGraph]:
        session = requests.Session()
        ids = _list_all_ids(session)

        # Resume support: skip IDs already on disk.
        out_dir = self.staging_dir()
        existing = set()
        if out_dir.exists():
            existing = {p.stem for p in out_dir.iterdir()
                        if p.suffix == ".graphml"}
        if existing:
            print(f"already staged: {len(existing):,} files (will skip)",
                  flush=True)

        for gid in tqdm(ids, desc="fetch + filter", unit="graph"):
            stem = f"houseofgraphs_{gid}"
            if stem in existing:
                continue
            G = _fetch_graph(session, gid)
            if G is None:
                time.sleep(REQUEST_DELAY_S)
                continue
            if not _passes_filter(G):
                time.sleep(REQUEST_DELAY_S)
                continue
            yield StagedGraph(name=stem, graph=G)
            time.sleep(REQUEST_DELAY_S)
