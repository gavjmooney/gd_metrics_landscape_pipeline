"""TOML-driven pipeline configuration.

A single ``config/pipeline.toml`` is the source of truth for every
stage. ``load(path)`` returns a frozen dataclass; stages read fields
from it directly.

Path strings support ``${VAR}`` and ``${VAR:-default}`` env-var
expansion so the same config works on Linux/WSL/CI without edits.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _expand_env(value: str) -> str:
    def repl(m: re.Match[str]) -> str:
        var, default = m.group(1), m.group(2)
        return os.environ.get(var, default if default is not None else "")
    return _ENV_VAR_RE.sub(repl, value)


@dataclass(frozen=True)
class GenerateConfig:
    count: int
    n_min: int
    n_max: int
    generators: list[str] | str
    max_retries: int


@dataclass(frozen=True)
class ValidateConfig:
    n_min: int
    n_max: int
    density_cap: str | float
    require_connected: bool
    require_simple: bool


@dataclass(frozen=True)
class SampleConfig:
    enabled: bool
    seed_offset: int
    caps: Mapping[str, int]


@dataclass(frozen=True)
class DedupConfig:
    enabled: bool
    method: str


@dataclass(frozen=True)
class LayoutsConfig:
    selected: list[str] | str
    exclude: list[str]


@dataclass(frozen=True)
class MetricsConfig:
    selected: list[str] | str


@dataclass(frozen=True)
class SourcesConfig:
    benchmark: list[str] | str
    real_world: list[str] | str
    graphs_with_drawings: list[str] | str


@dataclass(frozen=True)
class PipelineConfig:
    seed: int
    out_dir: Path
    parallel_workers: int
    generate: GenerateConfig
    validate: ValidateConfig
    sample: SampleConfig
    dedup: DedupConfig
    layouts: LayoutsConfig
    metrics: MetricsConfig
    sources: SourcesConfig
    source_path: Path = field(default_factory=Path)


def _require(d: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in d:
        raise ValueError(f"missing required field [{where}].{key}")
    return d[key]


def load(path: str | os.PathLike[str]) -> PipelineConfig:
    """Parse a pipeline TOML file into a frozen ``PipelineConfig``.

    Required top-level tables: ``pipeline``, ``generate``, ``validate``,
    ``sample``, ``dedup``, ``layouts``, ``metrics``, ``sources``. Missing
    fields raise :class:`ValueError` rather than silently falling back —
    config is the source of truth, drift between code defaults and the
    file would defeat the purpose.
    """
    p = Path(path)
    with p.open("rb") as f:
        raw = tomllib.load(f)

    pipe = _require(raw, "pipeline", "")
    out_dir = _expand_env(str(_require(pipe, "out_dir", "pipeline")))

    gen = _require(raw, "generate", "")
    val = _require(raw, "validate", "")
    smp = _require(raw, "sample", "")
    ddp = _require(raw, "dedup", "")
    lyt = _require(raw, "layouts", "")
    met = _require(raw, "metrics", "")
    src = _require(raw, "sources", "")

    return PipelineConfig(
        seed=int(_require(pipe, "seed", "pipeline")),
        out_dir=Path(out_dir),
        parallel_workers=int(_require(pipe, "parallel_workers", "pipeline")),
        generate=GenerateConfig(
            count=int(_require(gen, "count", "generate")),
            n_min=int(_require(gen, "n_min", "generate")),
            n_max=int(_require(gen, "n_max", "generate")),
            generators=_require(gen, "generators", "generate"),
            max_retries=int(_require(gen, "max_retries", "generate")),
        ),
        validate=ValidateConfig(
            n_min=int(_require(val, "n_min", "validate")),
            n_max=int(_require(val, "n_max", "validate")),
            density_cap=_require(val, "density_cap", "validate"),
            require_connected=bool(_require(val, "require_connected", "validate")),
            require_simple=bool(_require(val, "require_simple", "validate")),
        ),
        sample=SampleConfig(
            enabled=bool(_require(smp, "enabled", "sample")),
            seed_offset=int(_require(smp, "seed_offset", "sample")),
            caps=dict(smp.get("caps", {})),
        ),
        dedup=DedupConfig(
            enabled=bool(_require(ddp, "enabled", "dedup")),
            method=str(_require(ddp, "method", "dedup")),
        ),
        layouts=LayoutsConfig(
            selected=_require(lyt, "selected", "layouts"),
            exclude=list(lyt.get("exclude", [])),
        ),
        metrics=MetricsConfig(
            selected=_require(met, "selected", "metrics"),
        ),
        sources=SourcesConfig(
            benchmark=_require(src, "benchmark", "sources"),
            real_world=_require(src, "real_world", "sources"),
            graphs_with_drawings=_require(src, "graphs_with_drawings",
                                           "sources"),
        ),
        source_path=p.resolve(),
    )
