"""Metric registry — auto-discovers every algorithm module on import."""

from __future__ import annotations

import importlib
import pkgutil

from .base import (
    METRIC_REGISTRY, Metric, MetricContext, make_context, register_metric,
)


def _discover() -> None:
    for m in pkgutil.iter_modules(__path__):
        if m.name == "base":
            continue
        importlib.import_module(f"{__name__}.{m.name}")


_discover()


def get(name: str) -> Metric:
    if name not in METRIC_REGISTRY:
        raise KeyError(f"no metric {name!r}; "
                       f"available: {sorted(METRIC_REGISTRY)}")
    return METRIC_REGISTRY[name]


def available_metrics() -> list[str]:
    return sorted(METRIC_REGISTRY)


__all__ = [
    "METRIC_REGISTRY", "Metric", "MetricContext", "make_context",
    "register_metric", "get", "available_metrics",
]
