# graph-generation pipeline

Corpus generator for the *Effects of Structure on Layout* PhD project.
Produces a multi-cohort manifest of small-to-medium graphs (n ≤ 75)
with 24 properties per graph, 15 layouts per graph, and 11 readability
metrics per drawing.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate   # Linux/WSL/macOS
pip install -e .
cp config/pipeline.toml my-config.toml               # tweak as needed
EFFECTS_OUT=./output pipeline run all --config my-config.toml
```

On Windows, run inside WSL2 — the OGDF and HOLA backends need Linux
shared libs. A Docker image is provided for fully reproducible runs:

```bash
docker compose -f docker/docker-compose.yml run --rm \
    pipeline run all
```

### Native backends on a host install

`ogdf-python` (the FMMM / pivot-MDS / sugiyama / planarization-ortho /
radial-tree adapter) is on PyPI but loads `libOGDF.so` and `libCOIN.so`
at import time. If those aren't installed system-wide, point at a
local build with `OGDF_INSTALL_DIR`:

```bash
export OGDF_INSTALL_DIR=$HOME/adaptagrams/ogdf-build   # has lib/, include/
```

HOLA goes through a small CLI built from `tools/hola_cli.cpp`. Build
once against your `adaptagrams/cola` source tree:

```bash
ADAPTAGRAMS_DIR=$HOME/adaptagrams/cola \
    bash tools/build_hola_cli.sh        # writes .venv/bin/hola_cli
```

`_hola.py` resolves the binary via `$HOLA_CLI` or the `hola_cli` name
on PATH (the venv `bin/` is enough). Without either, the HOLA layout
is skipped with a `NotApplicable` reason.

## Pipeline DAG

```
generate -> stage -> sample -> dedup -> layout -> metrics
```

The `stage` stage parses every upstream source, applies size +
content + cap filters, computes the 24 manifest properties, and
writes graphmls directly to `graphs/<category>/<source>/`. (There
used to be a separate `promote` stage that re-read every staged
graphml; the merge halves the IO on slow filesystems.)

- `pipeline run all` — full chain
- `pipeline run <stage>` — one stage in isolation
- `pipeline run from:<stage>` — from this stage onward
- `pipeline plan` — print what would run, no side effects
- `pipeline backup --label foo` — ad-hoc manifest snapshot

Every stage is registered via a decorator in
`src/graph_generation/stages/<name>.py`. Layouts and metrics use the
same plugin pattern under `src/graph_generation/layouts/` and
`src/graph_generation/metrics/` — drop one file in, the dispatcher
picks it up.

## Configuration

`config/pipeline.toml` is the single source of truth. Override per-run
with `--config <path>`. All path values support `${VAR:-default}`
env-var expansion (e.g. `out_dir = "${EFFECTS_OUT:-./output}"`).

Key sections:
- `[pipeline]` — root seed, output dir, parallel workers
- `[generate]` — sampled corpus count, n bounds, generator selection
- `[validate]` — promotion filters (n bounds, density cap, connectivity)
- `[sample]` — per-source caps for stratified down-sampling
- `[dedup]` — `properties` (default, fast) or `wl_vf2` (rigorous)
- `[layouts]` / `[metrics]` — `"*"` (everything registered) or a list
- `[sources]` — per-cohort source selectors

## Reproducibility

Every deterministic stage seeds via `numpy.random.SeedSequence` from
the root `[pipeline].seed`. Run twice with the same seed and the same
config → byte-identical manifest, graphmls, and drawings (excluding
the wall-clock `generated_at_utc` column). Per-graph, per-layout, and
per-source seeds are **keyed by name** (graph_id, layout name, source
name) — adding or removing one item never re-rolls the seed of any
other.

External downloads (TUDataset, House of Graphs, SuiteSparse) are
**not** byte-pinned — they can change upstream. `drgraph` has no
seed flag and is intrinsically stochastic. BLAS thread count affects
last-bit numerical noise in iterative optimisers — pin
`OMP_NUM_THREADS=1` for strict reproducibility.

See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) for the full guarantee
matrix and the test coverage that pins it.

`pytest tests/test_reproducibility.py -m slow` exercises the full
pipeline twice and asserts identity.

## Adding a layout

```python
# src/graph_generation/layouts/my_layout.py
import networkx as nx
from .base import Layout, register_layout

def _my_layout(G, seed):
    return ({n: (x, y) for n in G.nodes(...)}, None)

LAYOUT = register_layout(Layout(
    name="my-layout", backend="native", fn=_my_layout, stochastic=True,
))
```

Then `pipeline run layout` picks it up. Same pattern for metrics.

## Project layout

```
config/pipeline.toml          # single source of truth
docker/                       # reproducible image + compose file
src/graph_generation/
  cli.py                      # `pipeline` console entry point
  config.py                   # TOML loader
  seeds.py                    # SeedSequence cascade
  manifest.py                 # schema, atomic append, path helpers
  stages/                     # generate, stage, promote, sample,
                              #   dedup, layout, metrics
  stagers/                    # per-source download/parse classes
  layouts/                    # one file per algorithm + backends
  metrics/                    # one file per metric
  generators/                 # 12 random/topology graph families
  properties.py               # 24 manifest invariants per graph
  validation.py               # config-driven cohort filters
  rescale.py                  # canonical coordinate scale
tests/
```
