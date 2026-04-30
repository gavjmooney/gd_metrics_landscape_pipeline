"""Post-generation validation — config-parameterised cohort constraints."""

from __future__ import annotations

import networkx as nx

from .config import ValidateConfig


def density_cap_piecewise(n: int) -> float:
    """Piecewise density cap by node count (PLAN.md §9.2).

    - n ≤ 8        → 1.0 (all densities; K_n canonical content)
    - 9 ≤ n ≤ 15   → 0.75
    - 16 ≤ n ≤ 30  → 0.6
    - n > 30       → 0.5 (Ghoniem hairball threshold)
    """
    if n <= 8:
        return 1.0
    if n <= 15:
        return 0.75
    if n <= 30:
        return 0.6
    return 0.5


def density_cap_for(n: int, mode: str | float) -> float:
    """Resolve the density cap for ``n`` from the config value.

    ``mode`` is either ``"piecewise"`` (the standard ladder above) or a
    fixed float cap applied uniformly.
    """
    if isinstance(mode, str):
        if mode == "piecewise":
            return density_cap_piecewise(n)
        return float(mode)
    return float(mode)


def is_valid(G: nx.Graph | None, vc: ValidateConfig | None = None) -> bool:
    """Connected, undirected, simple, no self-loops, density ≤ cap.

    ``vc`` provides the rules from config. When omitted the historical
    defaults apply (piecewise density, n ≥ 2, simple + connected).
    """
    if G is None:
        return False
    if vc is None:
        vc = _DEFAULT
    if G.is_directed():
        return False
    if vc.require_simple and G.is_multigraph():
        return False
    if G.number_of_nodes() < vc.n_min:
        return False
    if vc.n_max and G.number_of_nodes() > vc.n_max:
        return False
    if vc.require_simple and nx.number_of_selfloops(G) > 0:
        return False
    if vc.require_connected and not nx.is_connected(G):
        return False
    cap = density_cap_for(G.number_of_nodes(), vc.density_cap)
    if nx.density(G) > cap:
        return False
    return True


_DEFAULT = ValidateConfig(
    n_min=2, n_max=75, density_cap="piecewise",
    require_connected=True, require_simple=True,
)


# Back-compat shim for callers that still expect the bare aliases.
DENSITY_CAP = 0.5


def density_cap(n: int) -> float:  # noqa: F811
    return density_cap_piecewise(n)
