"""OpenFlights — per-country airport route subgraphs (topology only)."""

from __future__ import annotations

import csv
import io
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Iterator

import networkx as nx

from .base import Stager, StagedGraph, register_stager

AIRPORTS_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
ROUTES_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat"

AIRPORT_ID_COL = 0
AIRPORT_COUNTRY_COL = 3
ROUTE_SRC_ID_COL = 3
ROUTE_DST_ID_COL = 5


def _fetch(url: str, dst: Path) -> bytes:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as r:
        data = r.read()
    dst.write_bytes(data)
    return data


@register_stager
class OpenFlightsAirportsStager(Stager):
    """Per-country intra-country flight networks from the OpenFlights db."""

    source_name = "openflights_airports"

    def graphs(self) -> Iterator[StagedGraph]:
        archives_dir = (self.staging_root / "staging" / "_archives"
                        / "openflights")
        print(f"fetching {AIRPORTS_URL}")
        airports_raw = _fetch(AIRPORTS_URL, archives_dir / "airports.dat")
        print(f"fetching {ROUTES_URL}")
        routes_raw = _fetch(ROUTES_URL, archives_dir / "routes.dat")

        airport_country: dict[str, str] = {}
        for row in csv.reader(io.StringIO(
                airports_raw.decode("utf-8", errors="replace"))):
            if len(row) < 5:
                continue
            airport_country[row[AIRPORT_ID_COL]] = row[AIRPORT_COUNTRY_COL]

        by_country: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for row in csv.reader(io.StringIO(
                routes_raw.decode("utf-8", errors="replace"))):
            if len(row) <= ROUTE_DST_ID_COL:
                continue
            src = row[ROUTE_SRC_ID_COL]
            dst = row[ROUTE_DST_ID_COL]
            if src in ("\\N", "") or dst in ("\\N", ""):
                continue
            c_src = airport_country.get(src)
            c_dst = airport_country.get(dst)
            if c_src is None or c_dst is None or c_src != c_dst:
                continue
            u, v = (src, dst) if src < dst else (dst, src)
            by_country[c_src].add((u, v))

        for country, edge_set in sorted(by_country.items()):
            if not country:
                continue
            G = nx.Graph()
            # Iterate the edge set in sorted order so node insertion is
            # deterministic across processes — without this, hash-seed
            # randomisation makes ``add_edges_from(set(...))`` produce a
            # different node order per run, and the resulting graphml
            # (after convert_node_labels_to_integers) is reproducible
            # only within a single process. Cross-run comparison
            # previously found all 59 differing graphs in the corpus
            # came from this stager.
            G.add_edges_from(sorted(edge_set))
            n = G.number_of_nodes()
            if n < 2 or n > 75:
                continue
            G = nx.convert_node_labels_to_integers(G)
            G.graph.clear()
            slug = country.lower().replace(" ", "_").replace("/", "_")
            slug = "".join(ch for ch in slug if ch.isalnum() or ch == "_")
            if not slug:
                continue
            yield StagedGraph(name=f"of_{slug}", graph=G)
