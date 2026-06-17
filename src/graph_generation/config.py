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
    """``[generate]`` — sampled-cohort generation parameters."""

    # Target size of the sampled `generated/` cohort. The stage tops up
    # toward this number, retrying on each invalid draw until it hits the
    # target or 100 consecutive sampling failures abort the run.
    count: int

    # Inclusive node-count bounds for sampled draws. n is drawn uniformly
    # from [n_min, n_max] then a generator family eligible at that n is
    # picked by weight (`Generator.weight` in generators/__init__.py).
    n_min: int
    n_max: int

    # Generator selection. ``"*"`` includes every entry in the registry
    # (ER, BBA, NWS, SBM, LFR, GEO, HRG, tree_uniform, caterpillar,
    # planar_max, k_tree, k_regular). Otherwise a list of registry keys
    # restricts the family pool — useful for ablations.
    generators: list[str] | str

    # Retries per logical draw before giving up on that draw and moving
    # on (an LFR with bad params can fail to converge; HRG can produce
    # a disconnected graph). 100 consecutive whole-draw failures still
    # aborts the run.
    max_retries: int


@dataclass(frozen=True)
class ValidateConfig:
    """``[validate]`` — promotion-time filter rules.

    Applied to every staged graph before it earns a manifest row. The
    sampled cohort already passes these filters in :func:`is_valid`
    inside the generation loop; promote re-applies them on graphs
    fetched from external sources.
    """

    # Inclusive node-count bounds. The promote stage applies a
    # category-aware floor on top of n_min: real_world rejects n < 8
    # because n ≤ 7 is exhaustively enumerated by the calibration cohort
    # (and adds no new structural regime); benchmark and
    # graphs_with_drawings keep n ≥ n_min.
    n_min: int
    n_max: int

    # Maximum edge density. Either ``"piecewise"`` (the standard ladder
    # — 1.0 for n ≤ 8, 0.75 for 9..15, 0.6 for 16..30, 0.5 for n > 30)
    # or a fixed float applied uniformly. The piecewise ladder admits
    # dense small graphs (K_n through n=8) while keeping larger graphs
    # under the Ghoniem hairball threshold.
    density_cap: str | float

    # If true, disconnected graphs are rejected outright (we don't auto-
    # take the largest connected component — preserves the curator's
    # intent for benchmark / drawings cohorts).
    require_connected: bool

    # If true, multi-edges and self-loops are stripped at coercion time
    # (`nx.Graph(G)` and `nx.selfloop_edges`). Effectively always true
    # for our metric pipeline; exposed in case a future ablation needs
    # multigraph topology.
    require_simple: bool


@dataclass(frozen=True)
class StageConfig:
    """``[stage]`` — staging-time size filter and per-source caps.

    Layered on top of :class:`ValidateConfig`:
    - the size filter at staging mirrors ``validate.n_max`` and applies
      a category-aware floor (``real_world`` and ``benchmark`` skip n
      below ``n_min_real_world`` because exhaustive_small already
      covers n ≤ 7; ``graphs_with_drawings`` keeps everything down to
      ``validate.n_min`` because we want the curator's drawing even on
      a graph the sampled cohort already produces);
    - the per-source cap stops a single dataset from drowning the
      corpus with structurally-similar entries.
    """

    # Per-source upper bound on staged graphs. Sources not listed fall
    # back to ``default_cap``. Use ``0`` for "stage everything"
    # regardless of count.
    caps: Mapping[str, int]

    # Default cap applied to every source not in ``caps``. Set high
    # enough that small / curated sources flow through unchanged
    # (≈10k); the existing ``[sample.caps]`` does refined stratified
    # down-sampling on top.
    default_cap: int

    # Lower bound on staged graphs in the ``real_world`` and
    # ``benchmark`` cohorts. n < this is fully covered by the
    # exhaustive_small generation pass; staging them adds no new
    # structural regime. ``graphs_with_drawings`` ignores this floor
    # and uses ``validate.n_min`` instead.
    n_min_real_world: int


@dataclass(frozen=True)
class SampleConfig:
    """``[sample]`` — stratified down-sampling of capped real_world sources."""

    # When false, the sample stage is a no-op. Disable for an ablation
    # that wants the full real_world pool.
    enabled: bool

    # Offset into the SAMPLE leg of the seed cascade. Bumping this
    # produces a different sample without disturbing generation or
    # downstream stages — useful for cross-validation runs.
    seed_offset: int

    # Per-source row caps. Sources not listed are kept whole. Sources
    # already at-or-below their cap are kept whole. The stage stratifies
    # over (n_nodes, density) quintile bins (5×5 = 25 strata) and
    # samples proportionally with floor=1 per non-empty bin so the
    # source's distribution tails survive.
    caps: Mapping[str, int]


@dataclass(frozen=True)
class DedupConfig:
    """``[dedup]`` — cross-source isomorphism dedup."""

    # When false, the dedup stage is a no-op (every collision survives).
    enabled: bool

    # Algorithm choice:
    #   "properties" — group rows by the rounded 24-invariant tuple from
    #       the manifest; treat each non-singleton group as one iso
    #       class. Fast (~seconds on 100k rows), and 99%+ accurate
    #       because two non-iso graphs sharing all 24 invariants are
    #       functionally indistinguishable for the layout pipeline.
    #   "wl_vf2" — sub-bucket each property group by Weisfeiler-Lehman
    #       hash, then run VF2 isomorphism within each bucket. Rigorous,
    #       ~8 hours on the current corpus.
    method: str


@dataclass(frozen=True)
class LayoutsConfig:
    """``[layouts]`` — which layout algorithms run."""

    # ``"*"`` runs every algorithm registered in LAYOUT_REGISTRY (15 in
    # the canonical set). A list of names restricts to that subset —
    # useful for re-running just one algorithm after a bug fix.
    selected: list[str] | str

    # Names removed from the ``selected`` set. Defaults to
    # ``["sfdp", "twopi"]`` (the abandoned graphviz layouts dropped in
    # the refactor); add more during ablations.
    exclude: list[str]

    # When false, the layout stage skips writing drawing graphmls and
    # instead computes metrics in-memory immediately after each
    # layout, appending to ``metrics/<algo>.csv`` and the metrics
    # timings sidecar. Useful on slow filesystems where the
    # write-then-re-read cost dominates: ~halves layout+metrics IO
    # because each drawing is never serialised to disk.
    #
    # Trade-offs:
    #   - Re-running ``metrics`` no longer works (no drawings to read);
    #     a metrics-only re-run requires re-running ``layout`` too.
    #   - Per-graph drawings can no longer be inspected visually
    #     after the fact.
    #   - Idempotency on layout becomes graph_id-keyed via the metrics
    #     CSV (a row already there ⇒ skip) instead of a drawing file.
    #
    # When true (default), behaviour is unchanged: layout writes
    # drawings, the separate metrics stage reads them later.
    write_drawings: bool = True

    # Minimum number of drawing graphmls to keep per (cohort, source)
    # for visual verification, even when ``write_drawings=False``.
    # Group key: ``source`` for benchmark/real_world/graphs_with_drawings;
    # ``generator`` for generated/calibration cohorts (so each family
    # gets a sample). Picks the lexicographically-smallest graph_ids,
    # so the verification subset is deterministic and stable across
    # reruns. Set to 0 to disable (pure fused mode, no drawings at
    # all). Ignored when ``write_drawings=True`` since every drawing
    # is written anyway.
    verify_drawings_per_source: int = 5

    # Number of distinct layouts to run concurrently as separate
    # Python subprocesses. Each subprocess runs **one** layout
    # serially through the whole manifest — no within-layout fork
    # parallelism (which would hit the same fork-with-networkx-loaded
    # cliff that ``parallel_workers`` does). Different layouts share
    # no mutable state and no output files (each writes its own
    # metrics CSV + drawing subdir), so this scales near-linearly up
    # to ``min(physical cores, len(selected layouts))``. Set to 1 to
    # keep the canonical serial loop.
    parallel_layouts: int = 1


@dataclass(frozen=True)
class MetricsConfig:
    """``[metrics]`` — which readability metrics run."""

    # ``"*"`` runs every metric in METRIC_REGISTRY (11 in the canonical
    # set). A list restricts to a subset — saves time when only one
    # metric needs recomputation.
    selected: list[str] | str


@dataclass(frozen=True)
class SourcesConfig:
    """``[sources]`` — per-cohort source selectors for staging + promotion.

    Each cohort field is either ``"*"`` (every registered Source whose
    ``category`` matches the cohort) or a list of source names. Use a
    list to skip slow downloads (e.g. drop ``netzschleuder`` for a fast
    pipeline run).
    """
    benchmark: list[str] | str
    real_world: list[str] | str
    graphs_with_drawings: list[str] | str


@dataclass(frozen=True)
class PipelineConfig:
    """Full pipeline configuration — the parsed form of ``pipeline.toml``."""

    # Root seed for the SeedSequence cascade in :mod:`graph_generation.seeds`.
    # Every deterministic stage spawns its own independent stream from this
    # one integer; changing it perturbs every stage.
    seed: int

    # Corpus output root. Stages write into ``out_dir/graphs/``,
    # ``out_dir/drawings/<algo>/``, ``out_dir/metrics/``, and the
    # canonical ``out_dir/manifest.csv``. Path strings in the TOML
    # support ``${VAR:-default}`` env-var expansion so the same file
    # works on Linux/WSL/CI without edits.
    out_dir: Path

    # Process pool width for the per-stage parallel sections (per-graph
    # generation, per-source staging, per-source promotion, per-(graph,
    # layout) layout, per-drawing metrics). Set to 1 for serial /
    # debugging. Stages that touch the manifest serially (sample, dedup)
    # ignore this.
    parallel_workers: int

    # Per-stage configuration tables.
    generate: GenerateConfig
    validate: ValidateConfig
    stage: StageConfig
    sample: SampleConfig
    dedup: DedupConfig
    layouts: LayoutsConfig
    metrics: MetricsConfig
    sources: SourcesConfig

    # Resolved absolute path of the TOML file the config was loaded
    # from. Useful for stages that want to log "ran with config <path>"
    # or that need to resolve relative paths against the config file's
    # directory rather than the cwd.
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
    stg = _require(raw, "stage", "")
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
        stage=StageConfig(
            caps=dict(stg.get("caps", {})),
            default_cap=int(_require(stg, "default_cap", "stage")),
            n_min_real_world=int(_require(stg, "n_min_real_world", "stage")),
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
            write_drawings=bool(lyt.get("write_drawings", True)),
            verify_drawings_per_source=int(
                lyt.get("verify_drawings_per_source", 5)),
            parallel_layouts=int(lyt.get("parallel_layouts", 1)),
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
