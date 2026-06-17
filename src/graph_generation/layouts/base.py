"""Layout protocol, registry, and shared exception types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

import networkx as nx

Positions = Dict[Any, Tuple[float, float]]
Bends = Dict[Tuple[Any, Any], List[Tuple[float, float]]]
LayoutFn = Callable[[nx.Graph, int], Tuple[Positions, Optional[Bends]]]
ManifestPredicate = Callable[[Mapping[str, Any]], bool]


class NotApplicable(Exception):
    """Raised when an algorithm doesn't apply (e.g. planar on non-planar)."""


def _always_applicable(G: nx.Graph) -> bool:
    return True


@dataclass
class Layout:
    name: str
    backend: str
    fn: LayoutFn
    stochastic: bool = False
    applies_to: Callable[[nx.Graph], bool] = field(default=_always_applicable)
    # Per-graph wall-time cap. None = no cap. When set, ``_run_one`` runs
    # ``fn`` in a forked subprocess and hard-kills it on overrun. Use for
    # algorithms that can wedge inside C++ (OGDF) or shell out to a binary
    # whose own timeout we don't trust (HOLA): SIGALRM can't interrupt
    # those. Per-graph timeouts surface as a dedicated ``timeout`` outcome,
    # not ``fail`` — the graph is structurally fine, the algorithm just
    # ran out of budget.
    timeout_s: Optional[float] = None
    # Optional pre-filter evaluated against a manifest row (a dict from
    # ``manifest.csv``) — when set, the dispatcher uses this BEFORE
    # loading the graphml from disk so non-applicable graphs cost no IO.
    # Use for layouts whose applicability is fully determined by
    # manifest-recorded properties:
    #   radial-tree → row["is_tree"]
    #   planar      → row["is_planar"]
    #   curated     → row["category"] == "graphs_with_drawings"
    # Layouts that need to inspect the graph (e.g. degree distribution)
    # leave this None and fall back to the graph-level ``applies_to``.
    # The predicate must return True for "could apply"; runtime
    # ``applies_to`` is still a safety net for edge cases the manifest
    # column can't capture.
    manifest_applies_to: Optional[ManifestPredicate] = None


LAYOUT_REGISTRY: Dict[str, Layout] = {}


def register_layout(layout: Layout) -> Layout:
    if layout.name in LAYOUT_REGISTRY:
        raise ValueError(f"duplicate layout: {layout.name}")
    LAYOUT_REGISTRY[layout.name] = layout
    return layout
