"""SMACOF stress majorization (Gansner/Koren/North 2005)."""

from __future__ import annotations

import networkx as nx
import numpy as np

from .base import Layout, register_layout


def _stress_majorization(G: nx.Graph, seed: int):
    from scipy.sparse.linalg import cg

    nodes = list(G.nodes())
    n = len(nodes)
    idx = {nid: i for i, nid in enumerate(nodes)}
    dist = dict(nx.all_pairs_shortest_path_length(G))
    D = np.zeros((n, n))
    for u, dd in dist.items():
        for v, d in dd.items():
            D[idx[u], idx[v]] = d
    with np.errstate(divide="ignore", invalid="ignore"):
        W = np.where(D > 0, 1.0 / (D ** 2), 0.0)

    Lw = -W.copy()
    np.fill_diagonal(Lw, W.sum(axis=1))

    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, 2))

    _MAX_ITERS = 80
    _TOL = 1e-4
    prev_stress = None
    for _ in range(_MAX_ITERS):
        diff = X[:, None, :] - X[None, :, :]
        dij = np.linalg.norm(diff, axis=-1)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(dij > 1e-12, D / dij, 0.0)
        Lx = -W * ratio
        np.fill_diagonal(Lx, 0.0)
        np.fill_diagonal(Lx, -Lx.sum(axis=1))
        rhs = Lx @ X

        A = Lw[1:, 1:]
        b_x = rhs[1:, 0] - Lw[1:, 0] * X[0, 0]
        b_y = rhs[1:, 1] - Lw[1:, 0] * X[0, 1]
        X_new = X.copy()
        X_new[1:, 0], _ = cg(A, b_x, x0=X[1:, 0], rtol=1e-6)
        X_new[1:, 1], _ = cg(A, b_y, x0=X[1:, 1], rtol=1e-6)

        diff = X_new[:, None, :] - X_new[None, :, :]
        dij_new = np.linalg.norm(diff, axis=-1)
        stress = np.sum(W * (dij_new - D) ** 2) / 2.0

        X = X_new
        if prev_stress is not None and prev_stress - stress < _TOL * prev_stress:
            break
        prev_stress = stress

    return ({nodes[i]: (float(X[i, 0]), float(X[i, 1])) for i in range(n)},
            None)


LAYOUT = register_layout(Layout(
    name="stress-majorization", backend="native",
    fn=_stress_majorization, stochastic=True,
))
