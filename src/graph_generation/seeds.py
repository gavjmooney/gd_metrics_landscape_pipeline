"""Deterministic seed cascade.

One root seed (config.seed) spawns independent streams for each stage
via :class:`numpy.random.SeedSequence`. Stages spawn further per-unit
streams from their own SeedSequence so two parallel workers never
collide and a re-run with the same root seed reproduces every byte
of the deterministic part of the pipeline.

Cascade:

    root_seed
      ├── 0 generate
      ├── 1 sample
      ├── 2 dedup        (tie-breaking only)
      └── 3 layout
            ├── per-layout: SeedSequence.spawn(N_LAYOUTS)[i]
            │     └── per-graph: SeedSequence.spawn(N_GRAPHS)[j]
"""

from __future__ import annotations

from enum import IntEnum
from typing import Sequence

import numpy as np


class StageSeed(IntEnum):
    GENERATE = 0
    SAMPLE = 1
    DEDUP = 2
    LAYOUT = 3


def root(seed: int) -> np.random.SeedSequence:
    return np.random.SeedSequence(seed)


def stage(root_ss: np.random.SeedSequence, which: StageSeed
          ) -> np.random.SeedSequence:
    """Independent SeedSequence for one top-level stage."""
    return root_ss.spawn(len(StageSeed))[int(which)]


def per_unit(parent: np.random.SeedSequence, n: int
             ) -> Sequence[np.random.SeedSequence]:
    """N independent child sequences (e.g. one per graph or per layout)."""
    return parent.spawn(n)


def rng_from(ss: np.random.SeedSequence) -> np.random.Generator:
    """Get a Generator backed by a SeedSequence."""
    return np.random.default_rng(ss)
