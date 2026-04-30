"""Per-source stager registry — auto-discovery of stager modules."""

from __future__ import annotations

import importlib
import pkgutil

from .base import (
    StagedGraph, Stager, STAGER_REGISTRY, register_stager, stager_for,
)


def discover_stagers() -> None:
    """Import every submodule so its ``@register_stager`` decorators run."""
    for m in pkgutil.iter_modules(__path__):
        if m.name == "base":
            continue
        importlib.import_module(f"{__name__}.{m.name}")


__all__ = [
    "StagedGraph",
    "Stager",
    "STAGER_REGISTRY",
    "register_stager",
    "stager_for",
    "discover_stagers",
]
