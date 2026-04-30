"""Layout protocol, registry, and shared exception types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import networkx as nx

Positions = Dict[Any, Tuple[float, float]]
Bends = Dict[Tuple[Any, Any], List[Tuple[float, float]]]
LayoutFn = Callable[[nx.Graph, int], Tuple[Positions, Optional[Bends]]]


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


LAYOUT_REGISTRY: Dict[str, Layout] = {}


def register_layout(layout: Layout) -> Layout:
    if layout.name in LAYOUT_REGISTRY:
        raise ValueError(f"duplicate layout: {layout.name}")
    LAYOUT_REGISTRY[layout.name] = layout
    return layout
