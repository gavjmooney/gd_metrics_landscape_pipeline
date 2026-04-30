"""kruskal_stress — geg.kruskal_stress wrapper (uses cached APSP)."""

from __future__ import annotations

import geg

from .base import Metric, MetricContext, register_metric


def _kruskal_stress(G, ctx: MetricContext) -> float:
    return float(geg.kruskal_stress(G, apsp=ctx.apsp))


METRIC = register_metric(Metric(
    name="kruskal_stress", fn=_kruskal_stress,
    description="Stress between layout distances and graph-theoretic distances.",
))
