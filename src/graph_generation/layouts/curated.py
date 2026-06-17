"""Passthrough 'layout' over curator-supplied positions.

Graphs in the ``graphs_with_drawings`` cohort already carry ``x`` / ``y``
attributes from whoever drew them (Pajek vlad, gd_collection_v1
hand-laid samples, COIL-DEL embeddings, etc.). We want metric coverage
under those original positions alongside the algorithmic layouts —
every other Layout overwrites x/y with its own computed coordinates,
so the curator's drawing would otherwise vanish from the corpus.

This pseudo-layout is identity: it reads the existing x/y, returns
them unchanged, and lets the standard ``_run_one`` path apply the
canonical rescale + metric pass. ``applies_to`` returns True only
when every node has x and y, so the layout naturally short-circuits
to ``n/a`` on the synthetic / external cohorts that don't have
curator drawings.
"""

from __future__ import annotations

import networkx as nx

from .base import Layout, register_layout


def _has_curator_positions(G: nx.Graph) -> bool:
    if G.number_of_nodes() == 0:
        return False
    for _, attrs in G.nodes(data=True):
        if "x" not in attrs or "y" not in attrs:
            return False
    return True


def _curated(G: nx.Graph, seed: int):
    positions = {
        n: (float(attrs["x"]), float(attrs["y"]))
        for n, attrs in G.nodes(data=True)
    }
    # Curator drawings in our current sources are straight-edge — no
    # bend data is preserved on disk. If a future source carries edge
    # paths we can promote them here.
    return positions, None


def _manifest_is_drawing_cohort(row) -> bool:
    """Manifest-side pre-filter: only ``graphs_with_drawings`` carry
    curator x/y attributes.

    Topology cohorts (``generated``, ``calibration``, ``real_world``,
    ``benchmark``) write minimal graphml with no node attrs — the
    runtime ``_has_curator_positions`` check on those is guaranteed to
    return False, so we skip them without ever loading the file.
    Saves ~80k graphml loads on a 90k-row corpus.
    """
    return str(row.get("category", "")) == "graphs_with_drawings"


LAYOUT = register_layout(Layout(
    name="curated", backend="curated",
    fn=_curated, stochastic=False,
    applies_to=_has_curator_positions,
    manifest_applies_to=_manifest_is_drawing_cohort,
))
