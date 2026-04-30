"""aspect_ratio — geg.aspect_ratio wrapper (uses cached bbox)."""

from __future__ import annotations

import geg

from .base import Metric, MetricContext, register_metric


def _aspect_ratio(G, ctx: MetricContext) -> float:
    return float(geg.aspect_ratio(G, bbox=ctx.bbox))


METRIC = register_metric(Metric(
    name="aspect_ratio", fn=_aspect_ratio,
    description="Bounding-box aspect ratio of the drawing.",
))
