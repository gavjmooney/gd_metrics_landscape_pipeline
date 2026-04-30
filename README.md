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

## Pipeline DAG

```
generate -> stage -> promote -> sample -> dedup -> layout -> metrics
```

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
the wall-clock `generated_at_utc` column). External downloads
(TUDataset, House of Graphs, SuiteSparse) are **not** byte-pinned —
they can change upstream; that scope is intentionally excluded.

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
