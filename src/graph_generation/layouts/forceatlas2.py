"""ForceAtlas2 force-directed layout (Jacomy et al. 2014, Gephi)."""

from __future__ import annotations

import numpy as np
import networkx as nx

from ._native import to_pos_dict
from .base import Layout, NotApplicable, register_layout


def _forceatlas2(G: nx.Graph, seed: int):
    try:
        from fa2_modified import ForceAtlas2
    except ImportError as e:
        raise NotApplicable(f"fa2-modified not available: {e}") from e

    # The library does not accept a seed argument; reproducibility comes
    # from seeding the initial positions ourselves and passing them via
    # ``pos=...``.
    rng = np.random.default_rng(seed)
    initial = {n: (float(rng.random()), float(rng.random())) for n in G.nodes()}

    fa2 = ForceAtlas2(verbose=False)
    pos = fa2.forceatlas2_networkx_layout(G, pos=initial, iterations=100)
    return to_pos_dict(pos), None


LAYOUT = register_layout(Layout(
    name="forceatlas2", backend="native", fn=_forceatlas2, stochastic=True,
))
