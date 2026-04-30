"""Regular / near-regular families — random k-regular via the
configuration model."""

from __future__ import annotations

from typing import Any, Dict, Tuple

import networkx as nx
import numpy as np


def random_k_regular(n: int, rng: np.random.Generator) -> Tuple[nx.Graph, Dict[str, Any]]:
    """k uniform in [3, min(n-1, 8)]; parity fixed so k*n is even.
    NetworkX occasionally fails to terminate; raise and let the sampling
    layer retry with a fresh parameter draw.

    k floored at 3 because k=2 produces a cycle — only one such graph
    exists per n up to isomorphism, so k=2 draws at small n create
    duplicate-dominated clusters (post-25k dedup attributed 750 iso
    pairs to this). 2-regular is a structurally-distinctive regime that
    will be covered by the calibration cohort's cycles."""
    k_max = min(n - 1, 8)
    if k_max < 3:
        raise ValueError(f"random k-regular infeasible for n={n}")
    k = int(rng.integers(3, k_max + 1))
    if (k * n) % 2 == 1:
        k = k - 1 if k > 3 else k + 1
    if k < 3 or k > n - 1:
        raise ValueError(f"k={k} outside feasible range after parity fix for n={n}")

    seed = int(rng.integers(0, 2**31 - 1))
    G = nx.random_regular_graph(k, n, seed=seed)
    return G, {"k": k}
