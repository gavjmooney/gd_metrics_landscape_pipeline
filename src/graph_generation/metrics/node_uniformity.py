"""node_uniformity — geg.node_uniformity wrapper (uses cached bbox)."""

from __future__ import annotations

import geg

from .base import Metric, MetricContext, register_metric


def _node_uniformity(G, ctx: MetricContext) -> float:
    return float(geg.node_uniformity(G, bbox=ctx.bbox))


METRIC = register_metric(Metric(
    name="node_uniformity", fn=_node_uniformity,
    description="Evenness of node distribution across the bbox grid.",
))
