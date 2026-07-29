# graph-generation pipeline

Code for the paper *Does graph structure affect drawing quality?*
(Mooney, Wybrow, Purchase). The pipeline builds a corpus of small-to-medium
graphs (n ≤ 75) from generated, calibration, benchmark, real-world, and
curated-drawing sources, lays each graph out with every registered layout
algorithm, and computes readability metrics for every drawing. See the
paper for the methodology, cohort definitions, and analysis.

## Running the pipeline

```bash
python -m venv .venv && source .venv/bin/activate   # Linux/WSL/macOS
pip install -e .
EFFECTS_OUT=./output pipeline run all
```

The stages run as a fixed chain:

```
generate -> stage -> sample -> dedup -> layout -> metrics
```

- `pipeline run all` — full chain
- `pipeline run <stage>` — one stage in isolation
- `pipeline run from:<stage>` — from this stage onward
- `pipeline plan` — print what would run, no side effects

Outputs are written under `EFFECTS_OUT`: `manifest.csv` (one row per
graph, with all structural properties), `graphs/` (graph files per
cohort), `drawings/<algorithm>/`, and `metrics/<algorithm>.csv`.

On Windows, run inside WSL2 — the OGDF and HOLA backends need Linux
shared libraries. Alternatively, use the Docker image for a fully
pinned environment:

```bash
docker compose -f docker/docker-compose.yml run --rm pipeline run all
```

Two optional native backends need a one-off local build: HOLA
(`ADAPTAGRAMS_DIR=... bash tools/build_hola_cli.sh`) and DRGraph
(`bash tools/install_drgraph.sh`). If a backend is missing, its
layouts are skipped and recorded as `NotApplicable`; everything else
still runs. If OGDF's shared libraries are not installed system-wide,
point `OGDF_INSTALL_DIR` at a local build.

## Changing variables

All configuration lives in `config/pipeline.toml` (commented inline).
Copy it and pass `--config <path>` to override per run. The knobs you
are most likely to change:

- `[pipeline] seed` — root seed; every random choice derives from it,
  so the same seed and config reproduce the same corpus and drawings
  (external downloads and one unseedable layout, DRGraph, excepted).
- `[pipeline] out_dir` — output root (or set `EFFECTS_OUT`).
- `[generate] count`, `n_min`, `n_max`, `generators` — size and makeup
  of the generated cohort.
- `[validate]` — admission rules (node bounds, density cap,
  connectivity).
- `[sample.caps]` / `[stage.caps]` — per-source caps for the stratified
  down-sampling of large providers.
- `[layouts] selected` / `[metrics] selected` — `"*"` for everything
  registered, or an explicit list to run a subset.
- `[sources]` — per-cohort source selectors; e.g. `real_world = []`
  skips all external downloads for a fast local run.

Adding a layout or metric is a one-file plugin: drop a module into
`src/graph_generation/layouts/` or `src/graph_generation/metrics/`
following the `register_layout` / `register_metric` pattern of the
existing files, and the dispatcher picks it up.

## Reproducing the paper figures

`analysis/` contains the analysis for the paper, reading the released
corpus snapshot in `analysis/data/` (`manifest.csv` + one metrics CSV
per layout):

```bash
pip install -e ".[analysis]"
cd analysis
python paper_visualisations.py        # figs 1-4 -> analysis/figs/
python sankey_pipeline.py             # pipeline overview -> analysis/figs/
marimo edit paper_visualisations.py   # interactive exploration
```

`analysis/data_preprocessing.md` documents how the raw pipeline output
becomes the analysis-ready frames. `rebuild_sankey_overview.py`
regenerates the sankey's count sidecar and is only needed after a new
pipeline run (it reads audit files from the full run directory).

## Tests

```bash
pytest              # fast checks
pytest -m slow      # end-to-end reproducibility runs
```

## Citing

If you use this pipeline or corpus, please cite the paper. For
details of the graph sources (each with its original citation), see
`src/graph_generation/sources.py`.
