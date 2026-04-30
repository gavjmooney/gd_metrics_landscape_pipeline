"""Netzschleuder — single-net catalog and multi-net sub-net stagers."""

from __future__ import annotations

import csv
import io
import json
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterator

import networkx as nx

from ..validation import density_cap
from .base import Stager, StagedGraph, register_stager

API_LIST = "https://networks.skewed.de/api/nets?full=True"
API_NET = "https://networks.skewed.de/api/net/{slug}"
FILE_URL_SINGLE = "https://networks.skewed.de/net/{slug}/files/{slug}.csv.zip"
FILE_URL_SUB = "https://networks.skewed.de/net/{slug}/files/{sub_net}.csv.zip"

# Netzschleuder slugs already represented in the corpus by another path —
# previous classics stayed off netzschleuder via this list. football is
# size-rejected anyway; the rest were imported via networkx built-ins
# before the `classic` source was retired.
ALREADY_STAGED = {
    "karate", "lesmis", "davis_southern_women", "krackhardt_kite",
    "football",
}


def _est_undirected_density(n: int, m: int, is_directed: bool,
                            edge_reciprocity: float | None) -> float | None:
    if n < 2:
        return None
    if is_directed and edge_reciprocity is not None:
        m_u = m * (1 - edge_reciprocity / 2)
    elif is_directed:
        m_u = m * 0.75
    else:
        m_u = m
    max_edges = n * (n - 1) / 2
    return m_u / max_edges if max_edges > 0 else None


def _passes(a: dict) -> bool:
    n, m = a.get("num_vertices"), a.get("num_edges")
    if n is None or m is None or n < 2 or n > 75:
        return False
    if a.get("largest_component_fraction", 1.0) < 1.0:
        return False
    est_d = _est_undirected_density(
        n, m, a.get("is_directed", False), a.get("edge_reciprocity"))
    if est_d is not None and est_d > density_cap(n):
        return False
    return True


def _fetch(url: str, dst: Path) -> bytes:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return dst.read_bytes()
    with urllib.request.urlopen(url) as r:
        data = r.read()
    dst.write_bytes(data)
    return data


def _read_csv_zip(raw: bytes) -> nx.Graph:
    """Edges-only simple undirected graph from a Netzschleuder .csv.zip."""
    G = nx.Graph()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        edge_files = [n for n in zf.namelist() if n.endswith(".csv")
                      and ("edge" in n.lower())]
        if "edges.csv" in edge_files:
            edge_files = ["edges.csv"]
        for edge_name in edge_files:
            text = zf.read(edge_name).decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                src_key = next((k for k in row if k.strip("# ") == "source"), None)
                dst_key = next((k for k in row if k.strip("# ") == "target"), None)
                if src_key is None or dst_key is None:
                    continue
                u, v = row[src_key], row[dst_key]
                if u is None or v is None or u == "" or v == "":
                    continue
                try:
                    u, v = int(u), int(v)
                except (ValueError, TypeError):
                    pass
                G.add_edge(u, v)
    G.remove_edges_from(nx.selfloop_edges(G))
    G = nx.convert_node_labels_to_integers(G)
    G.graph.clear()
    return G


@register_stager
class NetzschleuderSingleNetStager(Stager):
    """Single-net catalog entries from Netzschleuder that pass the pre-filter."""

    source_name = "netzschleuder"

    def graphs(self) -> Iterator[StagedGraph]:
        archives_dir = (self.staging_root / "staging" / "_archives"
                        / "netzschleuder")
        print(f"fetching {API_LIST}")
        with urllib.request.urlopen(API_LIST) as r:
            nets = json.loads(r.read())
        print(f"  total catalog entries: {len(nets)}")

        candidates = []
        for slug, meta in nets.items():
            if slug in ALREADY_STAGED or meta.get("restricted", False):
                continue
            a = meta.get("analyses") or {}
            # multi-net catalogs have analyses keyed by sub-net name; skip them
            if "num_vertices" not in a:
                continue
            if not _passes(a):
                continue
            candidates.append(slug)
        print(f"  single-net candidates passing pre-filter: {len(candidates)}")

        for slug in candidates:
            url = FILE_URL_SINGLE.format(slug=slug)
            arch_path = archives_dir / f"{slug}.csv.zip"
            try:
                raw = _fetch(url, arch_path)
            except Exception as e:
                print(f"  fail[{slug}]: fetch error {type(e).__name__}: {e}")
                continue
            try:
                G = _read_csv_zip(raw)
            except Exception as e:
                print(f"  fail[{slug}]: parse error {type(e).__name__}: {e}")
                continue
            if G.number_of_edges() == 0:
                continue
            yield StagedGraph(name=slug, graph=G)


class _NetzschleuderCatalogStager(Stager):
    """Sub-nets of a multi-net Netzschleuder catalog."""

    def graphs(self) -> Iterator[StagedGraph]:
        slug = self.source.name.split("/", 1)[1]
        archives_dir = (self.staging_root / "staging" / "_archives"
                        / "netzschleuder" / slug)
        url = API_NET.format(slug=slug)
        print(f"fetching {url}")
        with urllib.request.urlopen(url) as r:
            meta = json.loads(r.read())
        sub_nets = meta.get("nets", [slug])
        analyses = meta.get("analyses", {})
        if "num_vertices" in analyses:
            raise RuntimeError(
                f"{slug!r} is a single-net catalog entry; this stager "
                f"only handles multi-net catalogs."
            )
        passing = [sn for sn in sub_nets if _passes(analyses.get(sn, {}))]
        print(f"  sub-nets passing pre-filter: {len(passing)}/{len(sub_nets)}")

        for sub_net in passing:
            file_url = FILE_URL_SUB.format(slug=slug, sub_net=sub_net)
            arch_path = archives_dir / f"{sub_net}.csv.zip"
            try:
                raw = _fetch(file_url, arch_path)
            except urllib.error.HTTPError as e:
                print(f"  fail[{sub_net}]: HTTP {e.code}")
                continue
            except Exception as e:
                print(f"  fail[{sub_net}]: {type(e).__name__}: {e}")
                continue
            try:
                G = _read_csv_zip(raw)
            except Exception as e:
                print(f"  fail[{sub_net}]: parse error {type(e).__name__}: {e}")
                continue
            if G.number_of_edges() == 0:
                continue
            # Filesystem-safe sub-net stem (paths can contain colons / slashes).
            safe = (sub_net.replace("/", "_")
                          .replace(":", "_")
                          .replace("\\", "_"))
            yield StagedGraph(name=safe, graph=G)


@register_stager
class NetzschleuderDomStager(_NetzschleuderCatalogStager):
    """DomArchive animal-dominance studies (Strauss et al. 2022)."""
    source_name = "netzschleuder/dom"


@register_stager
class NetzschleuderMorenoStager(_NetzschleuderCatalogStager):
    """Moreno's 1934 grade-level classroom sociograms."""
    source_name = "netzschleuder/moreno_sociograms"


@register_stager
class NetzschleuderDutchSchoolStager(_NetzschleuderCatalogStager):
    """Longitudinal Dutch secondary-school friendship snapshots."""
    source_name = "netzschleuder/dutch_school"


@register_stager
class NetzschleuderInternetTopPopStager(_NetzschleuderCatalogStager):
    """Internet Topology Zoo PoP-level graphs."""
    source_name = "netzschleuder/internet_top_pop"


@register_stager
class NetzschleuderMovieGalaxiesStager(_NetzschleuderCatalogStager):
    """Movie character co-appearance networks (moviegalaxies.com)."""
    source_name = "netzschleuder/moviegalaxies"
