"""FMMM (Hachul & Junger 2004) multilevel force-directed via OGDF.

Reproducibility caveat: even with PYTHONHASHSEED=0 and
``randSeed(seed)`` set explicitly below, OGDF's FMMM produces
non-bit-reproducible output across subprocess invocations.
Cross-process repro testing on the same input graph + same seed
yielded 3 distinct metric values in 3 subprocess runs. The
nondeterminism lives below the cppyy boundary (likely OGDF's
internal unseeded state, possibly OpenMP thread scheduling) and
isn't reachable from Python without forking the upstream library.
We accept it as inherent to the FMMM backend.
"""

from __future__ import annotations

import networkx as nx

from ._ogdf import extract_positions, import_ogdf, to_ogdf
from .base import Layout, register_layout


def _fmmm(G: nx.Graph, seed: int):
    ogdf, cppinclude = import_ogdf()
    cppinclude("ogdf/energybased/FMMMLayout.h")

    G_ogdf, GA, _, rev = to_ogdf(G)
    fm = ogdf.FMMMLayout()
    fm.useHighLevelOptions(True)
    fm.unitEdgeLength(30.0)
    fm.newInitialPlacement(True)
    fm.qualityVersusSpeed(ogdf.FMMMOptions.QualityVsSpeed.GorgeousAndEfficient)
    # OGDF's randSeed takes a signed C int (max 2^31-1) but the
    # SeedSequence cascade emits 32-bit unsigned values that overflow
    # ~50% of the time. Mask to 31 bits so every seed is accepted; the
    # transformation is deterministic so reproducibility is preserved.
    fm.randSeed(seed & 0x7FFFFFFF)
    fm.call(GA)
    return extract_positions(GA, rev), None


LAYOUT = register_layout(Layout(
    name="FMMM", backend="ogdf", fn=_fmmm, stochastic=True,
))
