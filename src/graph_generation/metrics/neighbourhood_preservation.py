"""neighbourhood_preservation — geg.neighbourhood_preservation wrapper."""

from __future__ import annotations

import geg

from .base import Metric, MetricContext, register_metric


def _neighbourhood_preservation(G, ctx: MetricContext) -> float:
    return float(geg.neighbourhood_preservation(G))


METRIC = register_metric(Metric(
    name="neighbourhood_preservation", fn=_neighbourhood_preservation,
    description="Jaccard overlap between graph k-NN and Euclidean k-NN.",
))
