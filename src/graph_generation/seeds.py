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
      │     └── per-source: keyed by source name
      ├── 2 dedup        (tie-breaking only)
      └── 3 layout
            ├── per-layout: keyed by layout name
            │     └── per-graph: keyed by graph_id

Per-layout, per-graph, and per-source seeds are derived as **pure
functions of (root_seed, name)** rather than spawn-index. Reordering,
adding, or removing one unit therefore does not perturb any other
unit's seed — a precondition for reproducibility under corpus drift.
See :func:`keyed` for the byte-derivation scheme.
"""

from __future__ import annotations

import hashlib
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
    """N independent child sequences (e.g. one per graph or per layout).

    Note: position-based — the i-th child shifts if N changes. Prefer
    :func:`keyed` for any case where the consumer is identifiable by a
    stable name (graph_id, layout name, source name).
    """
    return parent.spawn(n)


def rng_from(ss: np.random.SeedSequence) -> np.random.Generator:
    """Get a Generator backed by a SeedSequence."""
    return np.random.default_rng(ss)


def _key_to_words(*key_parts: str) -> tuple[int, ...]:
    """Hash an ordered tuple of names into a deterministic 8-tuple of
    32-bit unsigned ints suitable for SeedSequence's ``spawn_key``.

    Uses BLAKE2b over the UTF-8 bytes of each part separated by NUL,
    truncated to 32 bytes (= 8 × uint32). The choice is deterministic
    across machines, Python versions, and numpy versions; do not change
    it lightly — any change re-rolls every keyed seed in the project.
    """
    h = hashlib.blake2b(digest_size=32)
    for part in key_parts:
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    digest = h.digest()
    return tuple(int.from_bytes(digest[i:i + 4], "big")
                 for i in range(0, 32, 4))


def keyed(parent: np.random.SeedSequence, *key_parts: str
          ) -> np.random.SeedSequence:
    """Derive a child SeedSequence from a parent + a stable string key.

    Pure function of (parent_entropy, key_parts) — independent of any
    sibling stream's existence. Two consumers with different keys get
    independent streams; the same key under the same parent always
    yields the same child.

    Use whenever the consumer has a stable name (graph_id, layout
    name, source name): adding or removing a sibling will then never
    perturb this consumer's seed.
    """
    return np.random.SeedSequence(
        entropy=parent.entropy,
        spawn_key=tuple(parent.spawn_key) + _key_to_words(*key_parts),
    )


def keyed_int(parent: np.random.SeedSequence, *key_parts: str) -> int:
    """Convenience: :func:`keyed` reduced to a single 32-bit int.

    For consumers that take a plain integer seed (networkx, OGDF,
    Graphviz `start=`, RandomState). Returns ``np.uint32``-range
    (0..2**32-1); mask to 31 bits at the consumer if the C API only
    accepts a signed int (see fmmm.py).
    """
    return int(keyed(parent, *key_parts).generate_state(1)[0])
