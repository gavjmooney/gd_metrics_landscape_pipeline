"""WikiPathways GPML curated pathway diagrams (with author-saved layout)."""

from __future__ import annotations

import re
import shutil
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Iterator

import networkx as nx

from .base import Stager, StagedGraph, register_stager

INDEX_URL = "https://data.wikipathways.org/current/gpml/"

# A spread of model organisms; extend by adding species names.
SPECIES = [
    "Homo_sapiens", "Mus_musculus", "Rattus_norvegicus",
    "Saccharomyces_cerevisiae", "Caenorhabditis_elegans",
    "Drosophila_melanogaster", "Danio_rerio", "Arabidopsis_thaliana",
]


def _fetch_index() -> list[str]:
    with urllib.request.urlopen(INDEX_URL) as r:
        text = r.read().decode("utf-8", errors="replace")
    return sorted(set(re.findall(
        r'href="(wikipathways-\d+-gpml-[^"]+\.zip)"', text)))


def _download(url: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_size > 0:
        return
    print(f"downloading {url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "graph_generation"})
    with urllib.request.urlopen(req) as r, dst.open("wb") as f:
        shutil.copyfileobj(r, f, length=1024 * 1024)


def _parse_gpml(data: bytes) -> nx.Graph | None:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None

    by_tag: dict[str, list[ET.Element]] = {}
    for el in root.iter():
        tag = el.tag.split("}", 1)[-1]
        by_tag.setdefault(tag, []).append(el)

    node_pos: dict[str, tuple[float, float]] = {}
    node_attrs: dict[str, dict[str, str | float]] = {}
    for dn in by_tag.get("DataNode", []):
        gid = dn.attrib.get("GraphId")
        if not gid:
            continue
        for child in dn:
            if child.tag.split("}", 1)[-1] != "Graphics":
                continue
            try:
                x = float(child.attrib["CenterX"])
                y = float(child.attrib["CenterY"])
            except (KeyError, ValueError):
                continue
            node_pos[gid] = (x, y)
            attrs: dict[str, str | float] = {}
            for gname, key in (("Width", "width"), ("Height", "height")):
                try:
                    attrs[key] = float(child.attrib[gname])
                except (KeyError, ValueError):
                    pass
            for gname, key in (("Color", "color"), ("FillColor", "fill"),
                               ("ShapeType", "shape")):
                if gname in child.attrib:
                    attrs[key] = child.attrib[gname]
            if attrs:
                node_attrs[gid] = attrs
            break

    if not node_pos:
        return None

    edges: list[tuple[str, str, dict[str, object]]] = []
    for it in by_tag.get("Interaction", []):
        for child in it:
            if child.tag.split("}", 1)[-1] != "Graphics":
                continue
            refs: list[str] = []
            intermediate_pts: list[tuple[float, float]] = []
            for pt in child:
                if pt.tag.split("}", 1)[-1] != "Point":
                    continue
                ref = pt.attrib.get("GraphRef")
                if ref:
                    refs.append(ref)
                try:
                    px = float(pt.attrib["X"])
                    py = float(pt.attrib["Y"])
                    if not ref:
                        intermediate_pts.append((px, py))
                except (KeyError, ValueError):
                    pass
            if len(refs) >= 2:
                e_attrs: dict[str, object] = {}
                for gname, key in (("ConnectorType", "connector"),
                                   ("LineStyle", "line_style"),
                                   ("Color", "color")):
                    if gname in child.attrib:
                        e_attrs[key] = child.attrib[gname]
                if intermediate_pts:
                    e_attrs["bends"] = intermediate_pts
                edges.append((refs[0], refs[-1], e_attrs))
            break

    for gl in by_tag.get("GraphicalLine", []):
        for child in gl:
            if child.tag.split("}", 1)[-1] != "Graphics":
                continue
            refs = []
            for pt in child:
                if pt.tag.split("}", 1)[-1] != "Point":
                    continue
                ref = pt.attrib.get("GraphRef")
                if ref:
                    refs.append(ref)
            if len(refs) >= 2:
                edges.append((refs[0], refs[-1], {}))
            break

    G = nx.Graph()
    for gid, (x, y) in node_pos.items():
        G.add_node(gid, x=x, y=y, **node_attrs.get(gid, {}))
    for u, v, e_attrs in edges:
        if u in node_pos and v in node_pos and u != v:
            G.add_edge(u, v, **e_attrs)

    if G.number_of_edges() == 0:
        return None

    mapping = {old: i for i, old in enumerate(sorted(G.nodes))}
    H = nx.Graph()
    for old, new in mapping.items():
        H.add_node(new, **G.nodes[old])
    for u, v, data in G.edges(data=True):
        H.add_edge(mapping[u], mapping[v], **data)
    return H


@register_stager
class WikiPathwaysStager(Stager):
    """Curator-laid pathway diagrams from WikiPathways (CC0)."""

    source_name = "wikipathways"

    def graphs(self) -> Iterator[StagedGraph]:
        archives_dir = (self.staging_root / "staging-graphs-with-drawings"
                        / "_archives" / "wikipathways")
        print("fetching index ...")
        all_zips = _fetch_index()
        print(f"  {len(all_zips)} species zips available")

        for species in SPECIES:
            matches = [z for z in all_zips if f"gpml-{species}.zip" in z]
            if not matches:
                print(f"  species {species}: not in current release, skipping")
                continue
            zip_name = matches[0]
            url = INDEX_URL + zip_name
            archive_path = archives_dir / zip_name
            _download(url, archive_path)

            with zipfile.ZipFile(archive_path) as zf:
                gpml_names = [n for n in zf.namelist() if n.endswith(".gpml")]
                print(f"{species}: {len(gpml_names)} pathways")
                for name in gpml_names:
                    G = _parse_gpml(zf.read(name))
                    if G is None:
                        continue
                    stem = Path(name).stem
                    yield StagedGraph(
                        name=f"wp_{species.lower()}_{stem}", graph=G,
                    )
