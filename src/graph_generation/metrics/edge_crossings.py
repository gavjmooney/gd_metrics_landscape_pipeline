"""edge_crossings — uses cached score from MetricContext."""

from __future__ import annotations

from .base import Metric, MetricContext, register_metric


def _edge_crossings(G, ctx: MetricContext) -> float:
    return float(ctx.edge_crossings_score)


METRIC = register_metric(Metric(
    name="edge_crossings", fn=_edge_crossings,
    description="Edge-crossing count score (geg's normalisation).",
))
