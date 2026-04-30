"""Registry of graph-generator families.

Each family is a `Generator` record: name, minimum n below which it's
skipped, mixture weight, and a function that accepts `(n, rng)` and
returns `(nx.Graph, params_dict)`. The params dict is JSON-serialisable
and logged in the manifest so any graph can be regenerated from its seed.

HRG is registered with `enabled=False` — NetworkX lacks a first-class
hyperbolic random graph and a clean implementation is pending; add in a
coverage-topup pass if phase-1 analysis shows gaps in the power-law +
clustering + community corner of the property space.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple

import networkx as nx
import numpy as np

from . import classical, planar, regular, trees


GenerateFn = Callable[[int, np.random.Generator], Tuple[nx.Graph, Dict[str, Any]]]


@dataclass(frozen=True)
class Generator:
    name: str
    min_n: int
    weight: float
    generate: GenerateFn
    enabled: bool = True
    # If True, sampling routes the `generate` call through a subprocess
    # with a wall-clock timeout. Use for families with known
    # pathological-parameter hangs (LFR, HRG).
    guarded: bool = False
    timeout_s: float = 5.0


REGISTRY: List[Generator] = [
    # classical random
    Generator("er",           min_n=3,  weight=1.0, generate=classical.erdos_renyi),
    Generator("bba",          min_n=2,  weight=1.0, generate=classical.barabasi_albert),
    Generator("nws",          min_n=4,  weight=1.0, generate=classical.newman_watts_strogatz),
    Generator("sbm",          min_n=6,  weight=1.2, generate=classical.stochastic_block),
    # LFR — re-enabled behind subprocess timeout (NetworkX's implementation
    # otherwise hangs silently on pathological params).
    Generator("lfr",          min_n=20, weight=1.2, generate=classical.lfr,
              guarded=True, timeout_s=3.0),
    Generator("geo",          min_n=4,  weight=1.2, generate=classical.random_geometric),
    # HRG — custom implementation (no first-class NetworkX version).
    # Guarded because the pairwise-distance loop is O(n²) and an
    # unfavourable R can also produce disconnected graphs that slow the
    # retry loop. timeout is generous — n=75 needs ~30 ms worst case.
    Generator("hrg",          min_n=10, weight=1.2,
              generate=classical.hyperbolic_random,
              guarded=True, timeout_s=5.0),
    # trees
    Generator("tree_uniform", min_n=2,  weight=1.0, generate=trees.uniform_prufer),
    Generator("caterpillar",  min_n=4,  weight=0.8, generate=trees.caterpillar),
    # planar / treewidth
    Generator("planar_max",   min_n=4,  weight=1.5, generate=planar.random_maximal_planar),
    Generator("k_tree",       min_n=4,  weight=1.5, generate=planar.k_tree),
    # regular
    Generator("k_regular",    min_n=4,  weight=0.8, generate=regular.random_k_regular),
]


def enabled_registry() -> List[Generator]:
    return [g for g in REGISTRY if g.enabled]


def eligible_for(n: int) -> List[Generator]:
    return [g for g in enabled_registry() if g.min_n <= n]
