"""Schnyder planar embedding (only defined for planar graphs)."""

from __future__ import annotations

import networkx as nx

from ._native import to_pos_dict
from .base import Layout, NotApplicable, register_layout


def _planar(G: nx.Graph, seed: int):
    is_planar, _ = nx.check_planarity(G)
    if not is_planar:
        raise NotApplicable("graph is non-planar")
    return to_pos_dict(nx.planar_layout(G)), None


def _manifest_is_planar(row) -> bool:
    """Manifest-side pre-filter: row["is_planar"] is True.

    Mirrors radial-tree — the staging pass already ran the planarity
    check; reading the column skips the re-check on the ~50% of the
    corpus that is non-planar (saving the graphml load + a fresh
    nx.is_planar pass per graph).
    """
    v = row.get("is_planar")
    return v is True or str(v).strip().lower() == "true"


LAYOUT = register_layout(Layout(
    name="planar", backend="native", fn=_planar, stochastic=False,
    applies_to=lambda G: nx.is_planar(G),
    manifest_applies_to=_manifest_is_planar,
))
