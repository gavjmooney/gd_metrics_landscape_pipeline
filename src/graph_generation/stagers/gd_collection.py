"""GD-conference drawings collection.

Downloads the upstream ``.geg`` archive from
https://github.com/hegetim/gd-collection (one tarball, ~14 MB,
≈4,900 hand-tuned drawings spanning the GD00 through GD99 / GD24
proceedings folders) into ``staging-graphs-with-drawings/gd-collection-v1/<GDxx>/``,
then parses each via :func:`geg.read_geg` and yields it as a graph.

The download step is idempotent: a second run with the archive on
disk and the GD subfolders populated is a no-op.
"""

from __future__ import annotations

import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Iterator

import networkx as nx
from tqdm import tqdm

import geg

from .base import Stager, StagedGraph, register_stager


ARCHIVE_URL = "https://codeload.github.com/hegetim/gd-collection/tar.gz/refs/heads/main"


def _read_geg(path) -> nx.Graph | None:
    """Load a .geg drawing as a simple undirected Graph (canonicalised).

    Coercion only: undirected, no multi-edges, no self-loops, node
    labels renumbered 0..n-1. The drawing-side attributes (x, y, width,
    height, shape, colour) come along on the nodes; edge geometry rides
    along too. We hand the graph straight to :func:`geg.write_graphml`
    later so the yEd-flavoured graphml gets emitted intact.
    """
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
    return nx.relabel_nodes(G, mapping, copy=True)


def _download_archive(staging_root: Path) -> None:
    """Fetch and extract the upstream gd-collection tarball into staging.

    Lays files out as ``<staging_root>/<GDxx>/<file>.geg`` to match the
    pre-existing layout the original manual stage created.
    """
    if any(staging_root.glob("GD*/*.geg")):
        return  # already populated

    staging_root.mkdir(parents=True, exist_ok=True)
    print(f"[gd_collection_v1] downloading {ARCHIVE_URL}", flush=True)

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        archive_path = Path(tmp.name)
    try:
        req = urllib.request.Request(
            ARCHIVE_URL, headers={"User-Agent": "graph_generation"})
        with urllib.request.urlopen(req, timeout=120) as r, \
                archive_path.open("wb") as f:
            shutil.copyfileobj(r, f, length=1024 * 1024)

        with tarfile.open(archive_path, "r:gz") as tf:
            n_extracted = 0
            for m in tf.getmembers():
                if not m.isfile() or not m.name.endswith(".geg"):
                    continue
                rel = Path(m.name)  # gd-collection-main/geg/GD00/foo.geg
                # Find the "geg" anchor and pick GDxx + filename.
                try:
                    geg_idx = rel.parts.index("geg")
                except ValueError:
                    continue
                tail = rel.parts[geg_idx + 1:]  # ("GD00", "foo.geg") or deeper
                if len(tail) < 2:
                    continue
                gd_dir = tail[0]  # "GD00" .. "GD99"
                fname = tail[-1]
                out_dir = staging_root / gd_dir
                out_dir.mkdir(parents=True, exist_ok=True)
                fobj = tf.extractfile(m)
                if fobj is None:
                    continue
                (out_dir / fname).write_bytes(fobj.read())
                n_extracted += 1
        print(f"[gd_collection_v1] extracted {n_extracted} .geg files "
              f"into {staging_root}")
    finally:
        try:
            archive_path.unlink()
        except OSError:
            pass


@register_stager
class GDCollectionStager(Stager):
    """Download + parse the GD-collection ``.geg`` corpus.

    The base class's ``_write`` default already uses
    :func:`geg.write_graphml` for the ``graphs_with_drawings``
    cohort, so the yEd-flavoured drawing survives without an
    override here.
    """

    source_name = "gd_collection_v1"

    def graphs(self) -> Iterator[StagedGraph]:
        # Cache the upstream .geg files separately from the final
        # graphml output so re-staging doesn't re-download them.
        cache_dir = (self.staging_root / "staging"
                      / "_cache" / "gd-collection-v1")
        _download_archive(cache_dir)
        files = sorted(cache_dir.rglob("*.geg"))
        print(f"[gd_collection_v1] cached .geg files: {len(files)}")
        for path in tqdm(files, unit="graph", desc=self.source_name):
            year = path.parent.name  # "GD00" .. "GD99" / "GD23I" / "GD24"
            G = _read_geg(path)
            if G is None:
                continue
            yield StagedGraph(
                name=f"gd_{year.lower()}_{path.stem}",
                graph=G,
                upstream_id=str(path.relative_to(cache_dir)),
            )
