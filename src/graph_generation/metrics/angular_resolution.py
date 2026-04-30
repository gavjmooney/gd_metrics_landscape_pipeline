"""angular_resolution — geg.angular_resolution_min_angle wrapper."""

from __future__ import annotations

import geg

from .base import Metric, MetricContext, register_metric


def _angular_resolution(G, ctx: MetricContext) -> float:
    return float(geg.angular_resolution_min_angle(G))


METRIC = register_metric(Metric(
    name="angular_resolution", fn=_angular_resolution,
    description="Minimum angle between incident edges, normalised to [0, 1].",
))
