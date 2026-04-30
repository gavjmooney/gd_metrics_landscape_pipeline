"""Plugin-style layout registry — auto-discovers algorithm modules."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import List

from .base import (
    Bends,
    LAYOUT_REGISTRY,
    Layout,
    LayoutFn,
    NotApplicable,
    Positions,
    register_layout,
)

_PKG_DIR = Path(__file__).resolve().parent
_SKIP = {"__init__", "base"}

for _modinfo in pkgutil.iter_modules([str(_PKG_DIR)]):
    _name = _modinfo.name
    if _name.startswith("_") or _name in _SKIP:
        continue
    importlib.import_module(f"{__name__}.{_name}")


def get(name: str) -> Layout:
    if name not in LAYOUT_REGISTRY:
        available = ", ".join(sorted(LAYOUT_REGISTRY))
        raise KeyError(f"no layout {name!r}; available: {available}")
    return LAYOUT_REGISTRY[name]


def available_layouts() -> List[str]:
    return sorted(LAYOUT_REGISTRY)


__all__ = [
    "Bends",
    "LAYOUT_REGISTRY",
    "Layout",
    "LayoutFn",
    "NotApplicable",
    "Positions",
    "available_layouts",
    "get",
    "register_layout",
]
