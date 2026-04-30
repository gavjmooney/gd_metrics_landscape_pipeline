"""Stage protocol and shared pipeline context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Type

import numpy as np

from ..config import PipelineConfig


@dataclass
class PipelineContext:
    """Per-run state passed to every stage.

    ``out_dir`` is the resolved output root (config.out_dir + env vars).
    ``manifest_path`` is ``out_dir/manifest.csv``. ``root_ss`` is the
    numpy SeedSequence root for the cascade in :mod:`graph_generation.seeds`.
    """
    config: PipelineConfig
    out_dir: Path
    manifest_path: Path
    root_ss: np.random.SeedSequence
    extras: Dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_config(cls, cfg: PipelineConfig) -> "PipelineContext":
        out = cfg.out_dir.expanduser().resolve()
        return cls(
            config=cfg,
            out_dir=out,
            manifest_path=out / "manifest.csv",
            root_ss=np.random.SeedSequence(cfg.seed),
        )


class Stage(ABC):
    """Base class for a pipeline stage.

    Subclasses set ``name`` and override :meth:`run`. The runner picks
    them up via ``register_stage``.
    """

    name: str = ""
    parallel: bool = False
    idempotent: bool = True

    @abstractmethod
    def run(self, ctx: PipelineContext) -> None: ...

    def __repr__(self) -> str:
        return f"<Stage {self.name}>"


STAGE_REGISTRY: Dict[str, Type[Stage]] = {}


def register_stage(cls: Type[Stage]) -> Type[Stage]:
    if not getattr(cls, "name", ""):
        raise ValueError(f"stage class {cls.__name__} must set 'name'")
    if cls.name in STAGE_REGISTRY:
        raise ValueError(f"duplicate stage name: {cls.name}")
    STAGE_REGISTRY[cls.name] = cls
    return cls
