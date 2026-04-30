"""Metric plugin protocol — one file per metric, decorator-registered."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import networkx as nx


MetricFn = Callable[[nx.Graph, "MetricContext"], float]


@dataclass
class MetricContext:
    """Cached intermediates shared across metrics for one drawing.

    geg's bbox / crossings / APSP are expensive — compute once per
    drawing and pass to each metric that needs them. ``edge_crossings_score``
    is the value emitted by edge_crossings; cached so the metric
    function is a pure read.
    """
    bbox: Optional[Any] = None
    crossings: Optional[Any] = None
    edge_crossings_score: float = float("nan")
    apsp: Optional[Any] = None


@dataclass
class Metric:
    name: str
    fn: MetricFn
    description: str = ""


METRIC_REGISTRY: Dict[str, Metric] = {}


def register_metric(metric: Metric) -> Metric:
    if metric.name in METRIC_REGISTRY:
        raise ValueError(f"duplicate metric: {metric.name}")
    METRIC_REGISTRY[metric.name] = metric
    return metric


def make_context(G: nx.Graph) -> MetricContext:
    """Compute the shared intermediates for one drawing."""
    import geg
    ctx = MetricContext()
    try:
        ctx.bbox = geg.get_bounding_box(G)
    except Exception:
        ctx.bbox = None
    try:
        ctx.edge_crossings_score, ctx.crossings = \
            geg.edge_crossings(G, return_crossings=True)
        ctx.edge_crossings_score = float(ctx.edge_crossings_score)
    except Exception:
        ctx.edge_crossings_score = float("nan")
        ctx.crossings = None
    try:
        ctx.apsp = geg.graph_properties.compute_apsp(G)
    except Exception:
        ctx.apsp = None
    return ctx
