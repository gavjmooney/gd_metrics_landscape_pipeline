"""NDEx Network Data Exchange — networks with curator-saved layouts."""

from __future__ import annotations

import json
import urllib.request
from typing import Iterator

import networkx as nx

from .base import Stager, StagedGraph, register_stager

SEARCH_URL = "https://www.ndexbio.org/v2/search/network"
NETWORK_URL = "https://www.ndexbio.org/v2/network/{uuid}"

PERMISSIVE_LICENCES = [
    "cc0", "cc-0", "public domain", "waiver",
    "cc-by", "cc-by-sa", "cc by", "creativecommons.org/licenses/by",
]

# Vary the search query to broaden the pool — NDEx pagination is per-query.
_SEARCH_QUERIES = [
    "*", "signaling", "pathway", "interaction", "cancer", "protein",
    "network", "genes", "metabolism", "expression", "biological", "graph",
]
DEFAULT_LIMIT = 200
DEFAULT_MAX_PAGES = 50


def _post_json(url: str, body: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "User-Agent": "graph_generation"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "graph_generation"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))


def _search_page(offset: int, size: int = 100,
                 search_string: str = "*") -> list[dict]:
    doc = _post_json(
        f"{SEARCH_URL}?size={size}&offset={offset}",
        {"searchString": search_string},
    )
    return doc.get("networks", [])


def _licence_of(network: dict) -> str:
    for p in network.get("properties", []) or []:
        pred = (p.get("predicateString") or "").lower()
        if "rights" in pred or pred in ("license", "licence"):
            return (p.get("value") or "").strip()
    return ""


def _is_permissive(licence_str: str) -> bool:
    low = licence_str.lower()
    return any(m in low for m in PERMISSIVE_LICENCES)


def _parse_cx_any(doc: list) -> nx.Graph | None:
    """Build a graph with x/y from a CX1 or CX2 NDEx document."""
    node_pos: dict[int, tuple[float, float]] = {}
    edges: list[tuple[int, int]] = []
    for aspect in doc:
        if not isinstance(aspect, dict):
            continue
        if "nodes" in aspect:
            for n in aspect["nodes"]:
                nid_raw = n.get("id") if "id" in n else n.get("@id")
                if nid_raw is None:
                    continue
                try:
                    nid = int(nid_raw)
                except (TypeError, ValueError):
                    continue
                x, y = n.get("x"), n.get("y")
                if x is not None and y is not None:
                    try:
                        node_pos[nid] = (float(x), float(y))
                    except (TypeError, ValueError):
                        pass
        if "cartesianLayout" in aspect:
            for p in aspect["cartesianLayout"]:
                nid_raw = p.get("node")
                if nid_raw is None:
                    continue
                try:
                    nid = int(nid_raw)
                    x = float(p["x"])
                    y = float(p["y"])
                except (KeyError, TypeError, ValueError):
                    continue
                node_pos[nid] = (x, y)
        if "edges" in aspect:
            for e in aspect["edges"]:
                try:
                    s = int(e["s"])
                    t = int(e["t"])
                except (KeyError, TypeError, ValueError):
                    continue
                edges.append((s, t))
    if not node_pos:
        return None
    G = nx.Graph()
    for nid, (x, y) in node_pos.items():
        G.add_node(nid, x=x, y=y)
    for s, t in edges:
        if s in node_pos and t in node_pos and s != t:
            G.add_edge(s, t)
    if G.number_of_edges() == 0:
        return None
    mapping = {old: i for i, old in enumerate(sorted(G.nodes))}
    H = nx.Graph()
    for old, new in mapping.items():
        H.add_node(new, x=G.nodes[old]["x"], y=G.nodes[old]["y"])
    for u, v in G.edges:
        H.add_edge(mapping[u], mapping[v])
    return H


@register_stager
class NDExStager(Stager):
    """NDEx networks with hasLayout=true, permissive licence, 2 <= n <= 75."""

    source_name = "ndex"

    def graphs(self) -> Iterator[StagedGraph]:
        seen_uuids: set[str] = set()
        n_downloaded = 0
        n_parsed = 0

        search_iter = []
        for q in _SEARCH_QUERIES:
            for page in range(DEFAULT_MAX_PAGES):
                search_iter.append((q, page * 100))

        for query, offset in search_iter:
            if n_downloaded >= DEFAULT_LIMIT:
                break
            try:
                networks = _search_page(offset, size=100, search_string=query)
            except Exception as e:
                print(f"  search {query!r}@{offset} failed: "
                      f"{type(e).__name__}: {e}")
                continue
            if not networks:
                continue
            for net in networks:
                if n_downloaded >= DEFAULT_LIMIT:
                    break
                if not net.get("hasLayout"):
                    continue
                n = int(net.get("nodeCount") or 0)
                if n < 2 or n > 75:
                    continue
                licence = _licence_of(net)
                if not _is_permissive(licence):
                    continue
                uuid = net["externalId"]
                if uuid in seen_uuids:
                    continue
                seen_uuids.add(uuid)
                name = net.get("name") or uuid
                try:
                    doc = _get_json(NETWORK_URL.format(uuid=uuid))
                except Exception as e:
                    print(f"  {uuid}: download failed "
                          f"({type(e).__name__}: {e})")
                    continue
                n_downloaded += 1
                G = _parse_cx_any(doc)
                if G is None:
                    continue
                slug_name = "".join(
                    c if c.isalnum() or c in "-_" else "_" for c in name
                )[:40]
                stem = f"ndex_{n_parsed:04d}_{slug_name}_{uuid}"
                yield StagedGraph(name=stem, graph=G)
                n_parsed += 1
