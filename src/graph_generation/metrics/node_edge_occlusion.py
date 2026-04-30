"""node_edge_occlusion — geg.node_edge_occlusion wrapper (uses cached bbox)."""

from __future__ import annotations

import geg

from .base import Metric, MetricContext, register_metric


def _node_edge_occlusion(G, ctx: MetricContext) -> float:
    return float(geg.node_edge_occlusion(G, bbox=ctx.bbox))


METRIC = register_metric(Metric(
    name="node_edge_occlusion", fn=_node_edge_occlusion,
    description="Fraction of edges occluded by non-incident nodes.",
))
