"""node_resolution — geg.node_resolution wrapper."""

from __future__ import annotations

import geg

from .base import Metric, MetricContext, register_metric


def _node_resolution(G, ctx: MetricContext) -> float:
    return float(geg.node_resolution(G))


METRIC = register_metric(Metric(
    name="node_resolution", fn=_node_resolution,
    description="Min pairwise node distance over the layout's diagonal.",
))
