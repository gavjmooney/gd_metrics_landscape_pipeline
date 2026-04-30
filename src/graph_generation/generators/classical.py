"""Classical random graph models — ER, BBA, NWS, SBM, LFR, GEO, HRG.

Each `fn(n, rng)` draws its parameters from the ranges specified in PLAN.md,
constructs the graph, and returns `(G, params)`. If a construction fails
(LFR convergence, infeasible parameter combination) the function raises;
the sampling layer catches and retries with a fresh draw.

The RNG is a numpy `Generator`. NetworkX constructors expecting a `seed=`
int receive a draw from `rng.integers`, so the full run is reproducible
from a single master seed.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Tuple

import networkx as nx
import numpy as np


DENSITY_CAP = 0.5


def _nx_seed(rng: np.random.Generator) -> int:
    return int(rng.integers(0, 2**31 - 1))


def erdos_renyi(n: int, rng: np.random.Generator) -> Tuple[nx.Graph, Dict[str, Any]]:
    """p ~ Beta(2, 3) rescaled into [2/n, density_cap]. Beta(2, 3) (mean 0.4)
    pushes the density distribution toward the 0.2–0.4 regime where the
    structural-constraint analysis has the most to say; earlier Beta(1, 3)
    biased too sparse. Many draws still produce disconnected graphs at
    small n; the sampling layer retries."""
    lo, hi = 2.0 / n, DENSITY_CAP
    p = lo + (hi - lo) * rng.beta(2.0, 3.0)
    G = nx.erdos_renyi_graph(n, p, seed=_nx_seed(rng))
    return G, {"p": float(p)}


def barabasi_albert(n: int, rng: np.random.Generator) -> Tuple[nx.Graph, Dict[str, Any]]:
    """BA with m_new in [2, max(2, n/10)]. Always connected.

    m_new is floored at 2 because m_new=1 produces a preferential-attachment
    tree — structurally redundant with `tree_uniform` and it pulls BBA's
    overall signature toward the tree regime it's not supposed to occupy."""
    m_max = max(2, n // 10)
    m = int(rng.integers(2, m_max + 1))
    m = min(m, n - 1)
    G = nx.barabasi_albert_graph(n, m, seed=_nx_seed(rng))
    return G, {"m": m}


def newman_watts_strogatz(n: int, rng: np.random.Generator) -> Tuple[nx.Graph, Dict[str, Any]]:
    """Ring lattice + long-range shortcuts. k_ring in [2, n/4], p_rewire
    in [0.1, 1]. The 0.1 floor prevents the graph collapsing to a plain
    ring lattice at low rewire probability (the post-25k dedup scan
    attributed 836 / 1723 iso-pairs to this collapse)."""
    k_max = max(2, n // 4)
    k = int(rng.integers(2, k_max + 1))
    k = k if k % 2 == 0 else k + 1
    k = min(k, n - 1 if (n - 1) % 2 == 0 else n - 2)
    p = 0.1 + 0.9 * float(rng.beta(1.0, 3.0))
    G = nx.newman_watts_strogatz_graph(n, k, p, seed=_nx_seed(rng))
    return G, {"k": int(k), "p": p}


def stochastic_block(n: int, rng: np.random.Generator) -> Tuple[nx.Graph, Dict[str, Any]]:
    """SBM with 2..min(n/3, 6) roughly-equal blocks. Within-block p in
    [0.3, 1] (Beta(2, 2) with a 0.3 floor); between-block p in
    [0.02, ~0.2] (Beta(1, 10) with a 0.02 floor).

    The floors substantially reduce disconnected-graph rejections — the
    pre-floor run lost 41% of SBM attempts to rejection. Blocks smaller
    than `min_per=3` make community structure degenerate."""
    b_max = min(max(2, n // 3), 6)
    n_blocks = int(rng.integers(2, b_max + 1))

    sizes = _random_partition(n, n_blocks, min_per=3, rng=rng)

    p_in = 0.3 + 0.7 * float(rng.beta(2.0, 2.0))
    p_out = 0.02 + 0.2 * float(rng.beta(1.0, 10.0))
    P = np.full((n_blocks, n_blocks), p_out)
    np.fill_diagonal(P, p_in)

    G = nx.stochastic_block_model(sizes, P.tolist(), seed=_nx_seed(rng))
    # SBM returns a graph with extra attrs; strip to a plain Graph
    G = nx.Graph(G)
    return G, {"sizes": sizes, "p_in": p_in, "p_out": p_out}


def lfr(n: int, rng: np.random.Generator) -> Tuple[nx.Graph, Dict[str, Any]]:
    """LFR benchmark — tunable communities + power-law degree. Brittle;
    may raise `nx.ExceededMaxIterations`, in which case the sampling
    layer retries with a fresh draw."""
    tau1 = float(rng.uniform(2.0, 3.0))
    tau2 = float(rng.uniform(1.5, 3.0))
    mu = float(rng.uniform(0.1, 0.5))
    avg_k = float(rng.uniform(4.0, min(8.0, n / 4.0)))
    min_c = max(3, n // 10)
    G = nx.LFR_benchmark_graph(
        n, tau1=tau1, tau2=tau2, mu=mu,
        average_degree=avg_k, min_community=min_c,
        seed=_nx_seed(rng), max_iters=500,
    )
    # LFR returns a multigraph-like thing occasionally; coerce + de-self-loop
    G = nx.Graph(G)
    G.remove_edges_from(nx.selfloop_edges(G))
    return G, {
        "tau1": tau1, "tau2": tau2, "mu": mu,
        "avg_degree": avg_k, "min_community": min_c,
    }


def random_geometric(n: int, rng: np.random.Generator) -> Tuple[nx.Graph, Dict[str, Any]]:
    """Random geometric graph in unit square. Radius drawn above the
    Gilbert connectivity threshold so most draws yield a connected
    graph (the pre-floor version rejected 55% of attempts, dominantly
    on disconnection).

    Gilbert's threshold: for n points uniform in [0,1]^2, the critical
    radius for connectivity with high probability is
    r_c ≈ sqrt(log(n) / (π n)). We floor at 1.2 × r_c."""
    r_crit = math.sqrt(1.2 * math.log(n) / (math.pi * n))
    r_max = math.sqrt(DENSITY_CAP)   # radius² ≈ density → cap ≈ 0.71
    r_crit = min(r_crit, r_max * 0.9)
    r = r_crit + (r_max - r_crit) * float(rng.beta(1.0, 3.0))
    G = nx.random_geometric_graph(n, r, seed=_nx_seed(rng))
    # strip positional attrs — we want structure only; drawing comes later
    for _, attrs in G.nodes(data=True):
        attrs.clear()
    return G, {"radius": r, "r_crit": r_crit}


def hyperbolic_random(n: int, rng: np.random.Generator) -> Tuple[nx.Graph, Dict[str, Any]]:
    """Hyperbolic random graph (Krioukov et al. 2010, threshold variant).

    Places n points in a hyperbolic disk of radius R with radial
    distribution ρ(r) ∝ sinh(α r) and uniform angle θ. Two nodes
    connect iff their hyperbolic distance ≤ R. With α ∈ (1/2, 1) the
    degree distribution is a power-law with exponent γ = 2α + 1.

    The hyperbolic-law of cosines for two points (r₁, θ₁), (r₂, θ₂):
        cosh(d) = cosh(r₁)·cosh(r₂) − sinh(r₁)·sinh(r₂)·cos(|θ₁ − θ₂|)

    R is chosen from the target average-degree approximation
    R ≈ 2·log(8 n / (π k_bar)). No temperature (pure threshold).

    Disconnected draws happen at low avg_k; the sampling layer retries.
    Wrapped in a subprocess guard so a pathological draw can't hang the
    whole run."""
    alpha = float(rng.uniform(0.55, 0.95))
    k_bar = float(rng.uniform(4.0, 10.0))
    R = 2.0 * math.log(8.0 * n / (math.pi * k_bar))

    # inverse CDF of ρ(r) = α·sinh(α r) / (cosh(α R) − 1):
    u = rng.random(n)
    arg = 1.0 + u * (math.cosh(alpha * R) - 1.0)
    # np.arccosh is vectorised
    r = np.arccosh(arg) / alpha
    theta = rng.uniform(0, 2 * math.pi, size=n)

    G = nx.Graph()
    G.add_nodes_from(range(n))
    cosh_R = math.cosh(R)
    # pairwise — O(n²) but n ≤ 75 so it's fine
    cosh_r = np.cosh(r)
    sinh_r = np.sinh(r)
    for i in range(n):
        for j in range(i + 1, n):
            dtheta = abs(theta[i] - theta[j])
            if dtheta > math.pi:
                dtheta = 2 * math.pi - dtheta
            cosh_d = cosh_r[i] * cosh_r[j] - sinh_r[i] * sinh_r[j] * math.cos(dtheta)
            if cosh_d <= cosh_R:
                G.add_edge(i, j)

    return G, {"alpha": alpha, "k_bar": k_bar, "R": R}


# -------------------- helpers --------------------

def _random_partition(total: int, parts: int, min_per: int, rng: np.random.Generator) -> list[int]:
    """Partition `total` into `parts` integers each >= `min_per`."""
    if parts * min_per > total:
        raise ValueError(f"cannot partition {total} into {parts} parts of at least {min_per}")
    remaining = total - parts * min_per
    # stars-and-bars via random dividers
    cuts = sorted(int(x) for x in rng.integers(0, remaining + 1, size=parts - 1))
    prev, pieces = 0, []
    for c in cuts:
        pieces.append(c - prev)
        prev = c
    pieces.append(remaining - prev)
    return [min_per + p for p in pieces]
