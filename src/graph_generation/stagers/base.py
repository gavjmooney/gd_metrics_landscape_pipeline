"""Stager protocol — per-source download/parse/write pipeline.

A :class:`Stager` is responsible for a single staging source: it
fetches the upstream archive (or queries an API), parses every graph,
and writes plain :class:`networkx.Graph` graphml files into
``staging/<source>/`` (or ``staging-graphs-with-drawings/<source>/``
for the layout-carrying cohort).

Promotion (Phase 5) reads from the staging directory and applies
filtering / coercion to undirected before writing into
``graphs/<category>/<source>/``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, Tuple, Type

import networkx as nx

from ..sources import Source


@dataclass
class StagedGraph:
    """One graph fresh out of a stager, before any promotion filtering."""
    name: str  # filename stem; no extension
    graph: nx.Graph


class Stager(ABC):
    """Base class for a per-source stager.

    Subclasses set ``source_name`` (key into the SOURCES registry) and
    implement :meth:`graphs`. The framework drives :meth:`stage` which
    iterates :meth:`graphs` and writes graphml files.
    """

    source_name: str = ""

    def __init__(self, source: Source, staging_root: Path):
        self.source = source
        self.staging_root = staging_root

    @abstractmethod
    def graphs(self) -> Iterator[StagedGraph]:
        """Yield each parsed graph from the upstream source."""
        ...

    def staging_dir(self) -> Path:
        """Directory under ``out/`` to write staged graphml into."""
        rel = self.source.staging_path or f"staging/{self.source.name}"
        return self.staging_root / rel

    def stage(self) -> int:
        """Run the staging pass, returning the number of graphs written."""
        out = self.staging_dir()
        out.mkdir(parents=True, exist_ok=True)
        n = 0
        for sg in self.graphs():
            path = out / f"{sg.name}.graphml"
            nx.write_graphml(sg.graph, path)
            n += 1
        return n


STAGER_REGISTRY: Dict[str, Type[Stager]] = {}


def register_stager(cls: Type[Stager]) -> Type[Stager]:
    if not getattr(cls, "source_name", ""):
        raise ValueError(f"stager {cls.__name__} must set 'source_name'")
    if cls.source_name in STAGER_REGISTRY:
        raise ValueError(f"duplicate stager source_name: {cls.source_name}")
    STAGER_REGISTRY[cls.source_name] = cls
    return cls


def stager_for(source: Source, staging_root: Path) -> Stager:
    """Look up the right stager for a source. The registry indexes by
    exact ``source.name``; the parametric TUDataset stager is registered
    under the prefix ``"TUDataset/"`` which any ``TUDataset/<NAME>`` entry
    resolves to."""
    if source.name in STAGER_REGISTRY:
        return STAGER_REGISTRY[source.name](source, staging_root)
    # Prefix lookup for TUDataset/* family
    for key in STAGER_REGISTRY:
        if key.endswith("/") and source.name.startswith(key):
            return STAGER_REGISTRY[key](source, staging_root)
    raise KeyError(f"no stager registered for source {source.name!r}")
