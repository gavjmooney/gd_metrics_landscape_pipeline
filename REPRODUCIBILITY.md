# Reproducibility

This document describes what the pipeline guarantees to be
bit-deterministic across runs, and where determinism is intentionally
not guaranteed (with the reason).

## Summary

| What                                              | Bit-deterministic? |
|---------------------------------------------------|--------------------|
| `manifest.csv` (excluding `generated_at_utc`)     | Yes                |
| `graphs/**/*.graphml`                             | Yes                |
| Layout output for OGDF / Graphviz / native backends | Yes (modulo BLAS) |
| `metrics/<layout>.csv`                            | Yes (modulo BLAS) |
| Layout output for `drgraph`                       | **No** (see below) |
| Staged content from external sources              | **No** (see below) |

"Yes (modulo BLAS)" means the pipeline derives every random choice
deterministically from the root seed, but iterative numerical
optimisers (kamada-kawai, MDS, stress majorization) can converge to
last-bit-different values depending on BLAS thread count and
reduction order. See [§3](#3-blas--threading-numerical-noise) for
how to pin those.

## What "deterministic" means here

One root seed (`config.seed` → `SeedSequence`) feeds an independent
substream into every stage via the cascade in
`src/graph_generation/seeds.py`. Per-graph, per-layout, and
per-source seeds are derived as **pure functions of (root_seed,
name)** rather than spawn-index — see `seeds.keyed`. The consequences:

- Adding a new layout to the registry does not change the seed of any
  existing layout.
- Adding/removing a graph from the manifest does not change the seed
  assigned to any other graph.
- Adding/removing a source does not change the kept set of any other
  source under stratified sampling.
- A graphml's node iteration order does not affect any layout's
  output (canonicalisation in `layouts/_native.canonicalise_node_order`
  is applied before every `layout.fn` call).
- Resuming an interrupted run — even after the manifest changes
  between the kill and the restart — produces a metric CSV identical
  to a single uninterrupted run on the new manifest, with all orphan
  rows pruned and all duplicate rows collapsed last-write-wins.

## Sources of non-determinism (and what to do about them)

### 1. `drgraph` is intrinsically stochastic and unseedable

The upstream `drgraph` binary (Vis) does not expose a `--seed` flag.
Two invocations on the same input will produce different layouts.
Documented in `src/graph_generation/layouts/drgraph.py:1-7`.

**Recommendation.** Treat `drgraph` rows as a noise floor: aggregate
across multiple runs rather than comparing single-run values, or
exclude `drgraph` from any analysis that depends on bit-identity.

### 2. External sources can drift between runs

Online graph repositories (TUDataset, House of Graphs, SuiteSparse,
NDEx, WikiPathways, etc.) are mutable. The maintainers can revise,
add, or remove graphs at any time. The pipeline downloads and stages
from these sources on demand, so a re-run on a different date may
stage a different set of graphs even with the same code and seed.

**Recommendation.**
- For research that depends on a specific corpus snapshot, archive
  the staged graphmls (`output/graphs/`) alongside the analysis.
- The Docker image (`docker/`) pins Python and library versions but
  does not pin upstream content; combine it with archived staged
  graphmls for full reproducibility.
- The `tests/test_reproducibility.py` test deliberately runs with
  `sources={benchmark: [], real_world: [], graphs_with_drawings: []}`
  so it exercises only the deterministic-by-construction stages.

### 3. BLAS / threading numerical noise

NumPy / SciPy delegate matrix algebra to BLAS (OpenBLAS or MKL on
most systems). Iterative optimisers (`kamada-kawai`, `pivot-MDS`,
`stress-majorization`, `spectral_layout`'s eigendecomposition) do
floating-point reductions whose order depends on the thread count
and the BLAS implementation. Two runs with the same seed but
different `OMP_NUM_THREADS` can converge to last-bit-different
positions, which then propagate into the metric CSVs.

**For strict reproducibility**, pin a single BLAS thread before
launching the pipeline:

```bash
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
pipeline run all
```

Trade-off: this slows the BLAS-bound layouts (`kamada-kawai` on the
larger graphs is the worst hit, ~3× on a 16-core box). For the rest
of the pipeline the parallelism is at the per-graph level via
`parallel_workers`, which is independent of BLAS threading.

### 4. Layout backends with no exposed seed

`drgraph` (covered in [§1](#1-drgraph-is-intrinsically-stochastic-and-unseedable))
is the only such backend in the current registry. Every other
stochastic layout (`fruchterman-reingold`, `random`, `FMMM`,
`stress-majorization`, `forceatlas2`, `sfdp`) accepts a seed and is
threaded by the cascade in `seeds.keyed`.

## What's tested

`tests/test_seeds.py`
- Per-graph seed is graph_id-keyed (T1) — adding/removing/reordering
  manifest rows does not change any graph's seed.
- Per-layout seed is layout-name-keyed (T2) — adding a new layout
  does not change any existing layout's seed.
- Per-source RNG is independent (T3) — removing a source does not
  change any other source's kept sample.
- Adding a new layout does not perturb existing per-graph seeds (T7).

`tests/test_layouts.py`
- For every native NetworkX-backed layout, two graphmls with shuffled
  node order produce identical positions after canonicalisation (T4).

`tests/test_resume_cleanup.py`
- Mid-run interrupt followed by resume produces a metric CSV
  byte-identical to a single uninterrupted run (T6).
- Manifest change between runs reconciles cleanly: kept rows
  preserved, removed rows dropped, added rows appended once, no
  duplicates (T5).
- Cleanup helpers handle orphans, duplicates, and idempotent re-runs.

`tests/test_properties.py`
- `crossing_number_lb_bipartite` regression (T8) — pinned values on
  K_{3,3}, K_{4,4}, C_4, K_4 lock the formula so future edits are
  explicit.

`tests/test_reproducibility.py`
- Full deterministic-subset pipeline produces byte-identical
  manifest hash and graphml file lists across two independent runs.

## Implementation notes

The byte derivation of keyed seeds (`seeds._key_to_words`) uses
BLAKE2b over UTF-8 bytes with NUL separators, truncated to 32 bytes.
**Do not change this scheme** without a corpus regeneration: any
change re-rolls every per-graph and per-layout seed.

The CSV cleanup primitives (`stages/_cleanup.py`) write to a
`.cleanup.tmp` sibling and atomically rename. The same retry helper
the layout stage uses for graphml writes (`_replace_with_retry`) is
inlined as `_atomic_replace` to keep the cleanup module
self-contained.
