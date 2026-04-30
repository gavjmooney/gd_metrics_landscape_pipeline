"""Pipeline stages.

Each stage is a class implementing :class:`base.Stage`. The :mod:`runner`
discovers them via the ``STAGE_REGISTRY`` populated when the modules in
this package are imported. Order is fixed (``STAGE_ORDER``) and matches
the Sankey narrative: generate → stage → promote → sample → dedup →
layout → metrics.
"""

from __future__ import annotations

from .base import PipelineContext, Stage, STAGE_REGISTRY, register_stage

STAGE_ORDER = (
    "generate",
    "stage",
    "promote",
    "sample",
    "dedup",
    "layout",
    "metrics",
)

__all__ = [
    "PipelineContext",
    "Stage",
    "STAGE_ORDER",
    "STAGE_REGISTRY",
    "register_stage",
]
