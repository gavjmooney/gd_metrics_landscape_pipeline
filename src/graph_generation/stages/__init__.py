"""Pipeline stages.

Each stage is a class implementing :class:`base.Stage`. The :mod:`runner`
discovers them via the ``STAGE_REGISTRY`` populated when the modules in
this package are imported. Order is fixed (``STAGE_ORDER``) and matches
the Sankey narrative: generate → stage → sample → dedup → layout →
metrics.

The merged ``stage`` stage handles both downloading + parsing AND the
filtering / property computation that the previous ``promote`` stage
did, in one pass per source. This eliminates the staging-tree IO hop
that dominated wall time on slow filesystems.
"""

from __future__ import annotations

from .base import PipelineContext, Stage, STAGE_REGISTRY, register_stage

STAGE_ORDER = (
    "generate",
    "stage",
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
