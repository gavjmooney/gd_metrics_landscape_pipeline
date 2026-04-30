"""edge_orthogonality — geg.edge_orthogonality wrapper."""

from __future__ import annotations

import geg

from .base import Metric, MetricContext, register_metric


def _edge_orthogonality(G, ctx: MetricContext) -> float:
    return float(geg.edge_orthogonality(G))


METRIC = register_metric(Metric(
    name="edge_orthogonality", fn=_edge_orthogonality,
    description="Mean alignment of edges to horizontal/vertical axes.",
))
