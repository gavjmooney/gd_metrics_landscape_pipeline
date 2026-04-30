"""edge_length_deviation — geg.edge_length_deviation wrapper."""

from __future__ import annotations

import geg

from .base import Metric, MetricContext, register_metric


def _edge_length_deviation(G, ctx: MetricContext) -> float:
    return float(geg.edge_length_deviation(G))


METRIC = register_metric(Metric(
    name="edge_length_deviation", fn=_edge_length_deviation,
    description="Coefficient of variation of edge lengths.",
))
