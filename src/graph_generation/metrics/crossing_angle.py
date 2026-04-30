"""crossing_angle — geg.crossing_angle wrapper (uses cached crossings)."""

from __future__ import annotations

import geg

from .base import Metric, MetricContext, register_metric


def _crossing_angle(G, ctx: MetricContext) -> float:
    return float(geg.crossing_angle(G, crossings=ctx.crossings))


METRIC = register_metric(Metric(
    name="crossing_angle", fn=_crossing_angle,
    description="Minimum angle at edge crossings (0 if no crossings).",
))
