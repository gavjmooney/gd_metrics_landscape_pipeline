"""Sampling loop — draws (n, family, params), generates, validates, retries."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import networkx as nx
import numpy as np

from .generators import Generator, eligible_for
from .subprocess_guard import guarded_generate
from .validation import is_valid


_TRACE = os.environ.get("GG_TRACE", "") == "1"


@dataclass
class Sampled:
    graph: nx.Graph
    generator: str
    seed: int
    params: Dict[str, Any]
    attempts: int


def sample_one(
    rng: np.random.Generator,
    n_min: int = 10,
    n_max: int = 50,
    max_retries: int = 40,
    stats: Optional[Dict[str, Dict[str, int]]] = None,
) -> Optional[Sampled]:
    """One independent draw: pick n, pick a generator eligible at that n,
    draw parameters, generate, validate. Retry up to `max_retries` times
    on failure (infeasible params, disconnected output, over-cap density,
    LFR non-convergence). Returns None if every retry fails.

    `stats`, if given, is mutated with per-generator `tried` and
    `succeeded` counts, allowing the caller to report retry-yield
    diagnostics without threading a return value through every path."""
    tried = stats.setdefault("tried", {}) if stats is not None else None
    succeeded = stats.setdefault("succeeded", {}) if stats is not None else None

    for attempt in range(1, max_retries + 1):
        n = int(rng.integers(n_min, n_max + 1))
        gens = eligible_for(n)
        if not gens:
            continue

        weights = np.array([g.weight for g in gens], dtype=float)
        weights /= weights.sum()
        gen: Generator = gens[int(rng.choice(len(gens), p=weights))]

        if tried is not None:
            tried[gen.name] = tried.get(gen.name, 0) + 1

        seed = int(rng.integers(0, 2**31 - 1))
        gen_rng = np.random.default_rng(seed)

        if _TRACE:
            sys.stderr.write(f"[trace] gen={gen.name} n={n} seed={seed}\n")
            sys.stderr.flush()

        t0 = time.perf_counter()
        try:
            if gen.guarded:
                G, params = guarded_generate(gen.name, n, seed, gen.timeout_s)
            else:
                G, params = gen.generate(n, gen_rng)
        except (nx.NetworkXError, nx.ExceededMaxIterations,
                ValueError, RuntimeError, NotImplementedError) as e:
            if _TRACE:
                sys.stderr.write(f"[trace]   {gen.name}: {type(e).__name__}: {str(e)[:80]}\n")
                sys.stderr.flush()
            continue
        elapsed = time.perf_counter() - t0
        if _TRACE and elapsed > 0.5:
            sys.stderr.write(f"[trace]   slow: {elapsed:.2f}s\n")
            sys.stderr.flush()

        if not is_valid(G):
            if _TRACE:
                import networkx as _nx
                why = ("disconnected" if not _nx.is_connected(G)
                       else f"density={_nx.density(G):.3f}"
                       if _nx.density(G) > 0.5 else "other")
                sys.stderr.write(f"[trace]   {gen.name}: invalid ({why})\n")
                sys.stderr.flush()
            continue

        if succeeded is not None:
            succeeded[gen.name] = succeeded.get(gen.name, 0) + 1

        # strip all attrs (graph/node/edge) — SBM's partition, LFR's community,
        # GEO's positions would otherwise trip the graphml writer
        G.graph.clear()
        for _, attrs in G.nodes(data=True):
            attrs.clear()
        for _, _, attrs in G.edges(data=True):
            attrs.clear()

        return Sampled(
            graph=G, generator=gen.name, seed=seed,
            params=params, attempts=attempt,
        )

    return None
