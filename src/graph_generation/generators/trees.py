"""Tree families — uniform random (Prüfer) and caterpillar."""

from __future__ import annotations

from typing import Any, Dict, Tuple

import networkx as nx
import numpy as np


def uniform_prufer(n: int, rng: np.random.Generator) -> Tuple[nx.Graph, Dict[str, Any]]:
    """Uniformly random labelled tree via decoding a random Prüfer sequence.
    Every labelled tree on n nodes has equal probability."""
    if n == 1:
        G = nx.Graph(); G.add_node(0); return G, {}
    if n == 2:
        G = nx.Graph(); G.add_edge(0, 1); return G, {}

    seq = rng.integers(0, n, size=n - 2).tolist()
    G = nx.from_prufer_sequence([int(x) for x in seq])
    return G, {"prufer_len": len(seq)}


def caterpillar(n: int, rng: np.random.Generator) -> Tuple[nx.Graph, Dict[str, Any]]:
    """Tree whose backbone is a path; remaining nodes are leaves attached
    uniformly at random to backbone nodes. Backbone length in [n/3, 2n/3]."""
    lo = max(2, n // 3)
    hi = max(lo, (2 * n) // 3)
    backbone_len = int(rng.integers(lo, hi + 1))
    backbone_len = min(backbone_len, n)

    G = nx.path_graph(backbone_len)
    if backbone_len < n:
        leaf_parents = rng.integers(0, backbone_len, size=n - backbone_len)
        for i, parent in enumerate(leaf_parents, start=backbone_len):
            G.add_edge(int(parent), int(i))

    return G, {"backbone_len": backbone_len}
