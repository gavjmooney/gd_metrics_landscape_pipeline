"""Small ecological food webs from networkrepository / Netzschleuder / KONECT."""

from __future__ import annotations

import bz2  # noqa: F401  -- tarfile uses it implicitly via mode='r:bz2'
import csv
import io
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterator

import networkx as nx

from .base import Stager, StagedGraph, register_stager

# (staged_name, fetch_kind, url)
FOOD_WEBS = [
    ("stmarks_marsh", "edges",
     "https://nrvis.com/download/data/eco/eco-stmarks.edges"),
    ("everglades", "edges",
     "https://nrvis.com/download/data/eco/eco-everglades.edges"),
    ("mangrove_wet", "edges",
     "https://nrvis.com/download/data/eco/eco-mangwet.edges"),
    ("florida_bay_whole", "edges",
     "https://nrvis.com/download/data/eco/eco-florida.edges"),
    ("little_rock_lake", "netzschleuder",
     "https://networks.skewed.de/net/foodweb_little_rock/files/foodweb_little_rock.csv.zip"),
    ("florida_bay_wet", "konect",
     "http://konect.cc/files/download.tsv.foodweb-baywet.tar.bz2"),
    ("florida_bay_dry", "konect",
     "http://konect.cc/files/download.tsv.foodweb-baydry.tar.bz2"),
]


def _fetch(url: str, dst: Path) -> bytes:
    dst.parent.mkdir(parents=True, exist_ok=True)
    # nrvis.com refuses default urllib UAs; supply a browser-like header.
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": ("Mozilla/5.0 (Python; graph_generation corpus "
                           "staging) AppleWebKit/537.36"),
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req) as r:
        data = r.read()
    dst.write_bytes(data)
    return data


def _load_edges_text(raw: bytes) -> nx.Graph:
    G = nx.Graph()
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line[0] in "#%":
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            u, v = int(parts[0]), int(parts[1])
        except ValueError:
            u, v = parts[0], parts[1]
        G.add_edge(u, v)
    G.remove_edges_from(nx.selfloop_edges(G))
    G = nx.convert_node_labels_to_integers(G)
    G.graph.clear()
    return G


def _load_netzschleuder_zip(raw: bytes) -> nx.Graph:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        name = next((n for n in zf.namelist() if n.endswith("edges.csv")), None)
        if name is None:
            name = next((n for n in zf.namelist()
                         if n.endswith(".csv") and "edge" in n.lower()), None)
        if name is None:
            raise ValueError("no edges.csv in Netzschleuder zip")
        text = zf.read(name).decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        G = nx.Graph()
        for row in reader:
            src_key = next((k for k in row if k.strip("# ") == "source"), None)
            dst_key = next((k for k in row if k.strip("# ") == "target"), None)
            if src_key is None or dst_key is None:
                continue
            u, v = row[src_key], row[dst_key]
            if u == "" or v == "":
                continue
            try:
                u, v = int(u), int(v)
            except ValueError:
                pass
            G.add_edge(u, v)
    G.remove_edges_from(nx.selfloop_edges(G))
    G = nx.convert_node_labels_to_integers(G)
    G.graph.clear()
    return G


def _load_konect_tarbz2(raw: bytes) -> nx.Graph:
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:bz2") as tf:
        member = next((m for m in tf.getmembers()
                       if m.name.rsplit("/", 1)[-1].startswith("out.")), None)
        if member is None:
            raise ValueError("no out.<slug> member in KONECT archive")
        fobj = tf.extractfile(member)
        data = fobj.read() if fobj else b""
    return _load_edges_text(data)


_LOADERS = {
    "edges": _load_edges_text,
    "netzschleuder": _load_netzschleuder_zip,
    "konect": _load_konect_tarbz2,
}


@register_stager
class FoodWebsStager(Stager):
    """Small predator-prey food webs from three different mirrors."""

    source_name = "food_webs"

    def graphs(self) -> Iterator[StagedGraph]:
        archives_dir = (self.staging_root / "staging" / "_archives"
                        / "food_webs")
        for staged_name, kind, url in FOOD_WEBS:
            print(f"fetching {url}")
            try:
                raw = _fetch(url, archives_dir / f"{staged_name}.raw")
                G = _LOADERS[kind](raw)
            except Exception as e:
                print(f"  skip {staged_name}: {type(e).__name__}: {e}")
                continue
            yield StagedGraph(name=staged_name, graph=G)
