"""Archive-download benchmarks (rome / north / random-dag)."""

from __future__ import annotations

import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Iterator

import networkx as nx

from .base import Stager, StagedGraph, register_stager


class _ArchiveBenchmarkStager(Stager):
    """Shared base for tarball-shipped GraphML benchmarks."""

    def _download(self, url: str, dst: Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and dst.stat().st_size > 0:
            return
        tmp = dst.with_suffix(dst.suffix + ".part")
        print(f"downloading {url}", flush=True)
        with urllib.request.urlopen(url) as r, tmp.open("wb") as f:
            shutil.copyfileobj(r, f, length=1024 * 1024)
        tmp.replace(dst)

    def _extract(self, archive: Path, target: Path, strip: str) -> None:
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:gz") as tf:
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                name = m.name
                if strip and name.startswith(strip):
                    name = name[len(strip):]
                if not name or name.startswith("/") or ".." in name.split("/"):
                    continue
                dst = target / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                src = tf.extractfile(m)
                if src is None:
                    continue
                with dst.open("wb") as out:
                    shutil.copyfileobj(src, out)

    def graphs(self) -> Iterator[StagedGraph]:
        meta = self.source
        archive_path = (self.staging_root / "staging" / "_archives"
                        / meta.archive_name)
        self._download(meta.url, archive_path)
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td)
            self._extract(archive_path, workdir, meta.strip_prefix or "")
            for path in sorted(workdir.rglob("*.graphml")):
                try:
                    G = nx.read_graphml(path)
                except Exception as e:
                    print(f"  skip {path.name}: {type(e).__name__}: {e}")
                    continue
                yield StagedGraph(name=path.stem, graph=G)


@register_stager
class RomeStager(_ArchiveBenchmarkStager):
    """11,534 small benchmark graphs from the University of Rome."""
    source_name = "rome"


@register_stager
class NorthStager(_ArchiveBenchmarkStager):
    """1,277 AT&T / North DAG benchmark graphs."""
    source_name = "north"


@register_stager
class RandomDagStager(_ArchiveBenchmarkStager):
    """Pregenerated random DAG companion benchmark."""
    source_name = "random-dag"
