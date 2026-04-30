"""Pajek `.net` files with vertex coordinates (graphs_with_drawings cohort)."""

from __future__ import annotations

import re
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Iterator, Optional, Tuple

import networkx as nx

from .base import Stager, StagedGraph, register_stager

ARCHIVE_URL = "https://github.com/bavla/Nets/archive/refs/heads/master.tar.gz"

# Pajek vertex line: id "name" [x y z [attrs...]]
_VERTEX_RE = re.compile(
    r"^\s*(\d+)\s+(?:\"([^\"]*)\"|(\S+))(.*)$"
)
_FLOAT_RE = re.compile(r"-?\d+\.\d+(?:[eE][+-]?\d+)?|-?\d+")


def _fetch(url: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_size > 0:
        return
    print(f"downloading {url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "graph_generation"})
    with urllib.request.urlopen(req) as r, dst.open("wb") as f:
        shutil.copyfileobj(r, f, length=1024 * 1024)


def _extract_net_files(archive: Path, dst_dir: Path) -> list[Path]:
    """Extract every .net file with a per-subfolder slug, return paths."""
    extracted: list[Path] = []
    with tarfile.open(archive, "r:gz") as tf:
        for m in tf.getmembers():
            if not m.isfile() or not m.name.endswith(".net"):
                continue
            rel = Path(m.name)
            try:
                i = rel.parts.index("Pajek")
                subfolder = "_".join(rel.parts[i + 1:-1])
            except ValueError:
                subfolder = ""
            slug = f"{subfolder}_{rel.stem}" if subfolder else rel.stem
            slug = re.sub(r"[^A-Za-z0-9._-]+", "_", slug).strip("_")
            out = dst_dir / f"{slug}.net"
            fobj = tf.extractfile(m)
            if fobj is None:
                continue
            out.write_bytes(fobj.read())
            extracted.append(out)
    return extracted


def _parse_net(path: Path) -> Tuple[Optional[nx.Graph], str]:
    """Parse a Pajek .net file. Returns (G, '') on success with x/y on every
    node, else (None, reason)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return None, f"read_error:{type(e).__name__}"

    lines = text.splitlines()
    vi = next((i for i, line in enumerate(lines)
               if line.strip().lower().startswith("*vertices")), None)
    if vi is None:
        return None, "no_vertices_section"
    header_toks = lines[vi].split()
    if len(header_toks) < 2:
        return None, "malformed_header"
    try:
        n = int(header_toks[1])
    except ValueError:
        return None, "malformed_header"

    vertices: dict[int, tuple[float, float]] = {}
    topology_only = False
    for j in range(vi + 1, min(vi + 1 + 5 * n, len(lines))):
        line = lines[j].strip()
        if not line or line.startswith("%"):
            continue
        if line.startswith("*"):
            break
        m = _VERTEX_RE.match(line)
        if not m:
            continue
        try:
            vid = int(m.group(1))
        except ValueError:
            continue
        coords = _FLOAT_RE.findall(m.group(4) or "")
        if len(coords) < 2:
            topology_only = True
            break
        try:
            x, y = float(coords[0]), float(coords[1])
        except ValueError:
            topology_only = True
            break
        vertices[vid] = (x, y)
        if len(vertices) >= n:
            break

    if topology_only or not vertices:
        return None, "topology_only"

    edges: list[tuple[int, int]] = []
    in_edges = False
    for j in range(vi + 1 + n, len(lines)):
        line = lines[j].strip()
        if not line or line.startswith("%"):
            continue
        if line.startswith("*"):
            low = line.lower()
            in_edges = (low.startswith("*edges") or low.startswith("*arcs")
                        or low.startswith("*edgeslist")
                        or low.startswith("*arcslist"))
            continue
        if not in_edges:
            continue
        toks = line.split()
        if len(toks) < 2:
            continue
        try:
            u, v = int(toks[0]), int(toks[1])
        except ValueError:
            continue
        edges.append((u, v))

    G = nx.Graph()
    for vid, (x, y) in vertices.items():
        G.add_node(vid, x=float(x), y=float(y))
    G.add_edges_from(edges)
    G.remove_edges_from(nx.selfloop_edges(G))
    mapping = {old: i for i, old in enumerate(sorted(G.nodes))}
    H = nx.Graph()
    for old, new in mapping.items():
        H.add_node(new, x=G.nodes[old]["x"], y=G.nodes[old]["y"])
    for u, v in G.edges:
        H.add_edge(mapping[u], mapping[v])
    return H, ""


@register_stager
class PajekStager(Stager):
    """Pajek .net files that ship with vertex coordinates for every node."""

    source_name = "pajek"

    def graphs(self) -> Iterator[StagedGraph]:
        archive = (self.staging_root / "staging-graphs-with-drawings"
                   / "_archives" / "pajek" / "bavla-nets-master.tar.gz")
        _fetch(ARCHIVE_URL, archive)
        with tempfile.TemporaryDirectory() as td:
            net_files = _extract_net_files(archive, Path(td))
            print(f"extracted {len(net_files)} .net files")
            for path in sorted(net_files):
                G, reason = _parse_net(path)
                if G is None:
                    continue
                yield StagedGraph(name=f"pajek_{path.stem}", graph=G)
