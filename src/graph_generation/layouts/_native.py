"""Helpers for native (networkx / numpy / scipy) layouts."""

from __future__ import annotations

from typing import Mapping, Tuple

from .base import Positions


def to_pos_dict(pos: Mapping) -> Positions:
    return {n: (float(xy[0]), float(xy[1])) for n, xy in pos.items()}
