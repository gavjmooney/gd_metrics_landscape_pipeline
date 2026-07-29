# Data preprocessing

This document explains, in plain language, how raw pipeline output is
turned into the analysis-ready data frames that the marimo notebooks
consume.

The code that does all of this lives in `analysis/data_prep.py`, with a
few extra in-notebook steps in `paper_visualisations.py`.

---

## 1. Where the raw data lives

The analysis reads a pipeline output directory — for the released
corpus this is `analysis/data/`. The shape is always:

```
analysis/data/
├── manifest.csv            ← one row per graph, with its structural properties
├── metrics\                ← one CSV per layout algorithm
│   ├── FMMM.csv
│   ├── HOLA.csv
│   ├── drgraph.csv
│   ├── ... (one file per layout the pipeline ran)
└── .analysis_cache\        ← created automatically when a notebook loads data
    ├── drawings.parquet
    ├── manifest.parquet
    └── envelopes.parquet
```

Layouts are discovered by file name. Adding a new layout to the
pipeline means a new CSV in `metrics/` and the loader picks it up
automatically. The drawings frame carries only the raw `layout`
id (e.g. `fruchterman-reingold`); families are assigned in the
notebooks via the layout-cluster slider (§5c).

---

## 2. What each raw file contains

### `manifest.csv` — one row per graph

Each row identifies one graph by its `graph_id` (e.g.
`caterpillar_n010_m0009_s88465874.graphml`) and lists every
structural property the analysis depends on. Twenty-four properties
live here:

- Sizes: `n_nodes`, `n_edges`, `density`
- Boolean classes: `is_planar`, `is_tree`, `is_bipartite`,
  `is_eulerian`, `is_regular`, `is_forest`
- Degree statistics: `min_degree`, `max_degree`, `mean_degree`,
  `degree_std`
- Distance statistics: `diameter`, `radius`,
  `avg_shortest_path_length`
- Clustering / structure: `n_triangles`, `average_clustering`,
  `transitivity`, `degree_assortativity`,
  `n_biconnected_components`, `degeneracy`
- Crossing-number lower bounds: `crossing_number_lb_euler`,
  `crossing_number_lb_bipartite`
- Cohort / source metadata used to slice the corpus.

Booleans are stored as Python `True`/`False`; numerics as floats or
ints; missing values come through as `NaN`.

### `metrics/<layout>.csv` — one row per (graph, layout) pair

For every layout the pipeline ran on a graph, there is one row in
that layout's CSV with the **11 normalised readability metrics**:

```
angular_resolution, aspect_ratio, crossing_angle,
edge_crossings, edge_length_deviation, edge_orthogonality,
kruskal_stress, neighbourhood_preservation,
node_edge_occlusion, node_resolution, node_uniformity
```

All metrics are scaled so that **higher is better** and the range is
`[0, 1]`. NaNs appear when a metric is undefined for a particular
drawing (e.g. some metrics aren't defined when there are no
crossings).

---

## 3. Building the `drawings` frame

This is the central data frame that almost every analysis cell
consumes. It is built by `load_drawings_from(pipeline_dir)` in
`data_prep.py`. The steps:

1. **Read the manifest** (`manifest.csv`) into a DataFrame.
2. **Walk `metrics/*.csv`.** For each CSV, read it and add a
   `layout` column with the file name (without the `.csv`),
   e.g. `"fruchterman-reingold"`.
3. **Concatenate** all the per-layout frames vertically. The result
   is long-form: one row per `(graph_id, layout)`.
4. **Merge** the manifest onto each row using `graph_id` as the key.
   Every row now carries both its metric values *and* the structural
   properties of the graph it was drawn from.
5. **Cache** the resulting frame as
   `.analysis_cache/drawings.parquet` so subsequent loads are
   instant.

After step 5, the in-memory frame has:

- 1 row per (graph, layout) — for a corpus of ~90 k graphs and 18
  layouts that's ~1.2 M rows.
- Columns: `graph_id`, `layout`, 11 metric columns, plus 24
  structural properties merged from the manifest.

---

## 4. The envelope frame: one row per graph

A second derived frame, built by `load_envelopes_from(pipeline_dir)`,
collapses the per-drawing rows into **one row per graph** with summary
statistics across that graph's layouts:

- `<metric>_min`   — the worst score any layout achieved on this graph.
- `<metric>_max`   — the best score any layout achieved on this graph
  (the **ceiling**).
- `<metric>_mean`  — the typical score across the graph's layouts
  (algorithm noise smoothed out, structural signal kept).
- `<metric>_range` = `max − min` — the **envelope width**: how much
  algorithm choice swings the metric on this graph.

Each row is then merged with the manifest so the per-graph
structural properties travel alongside the envelope statistics.

---

## 5. In-notebook preprocessing

The notebooks do a small amount of extra preprocessing before
plotting. These steps live in the notebooks (not in `data_prep.py`)
because they reflect *analysis decisions* rather than data shape.

### 5a. Two composite metrics

The 11 raw metrics are kept as-is, and the notebooks compute two
per-row composites alongside them:

- **`quality`** — uniform-weight mean of all 11 metrics (NaN-aware:
  missing metrics are skipped via `skipna=True`). A naive "overall
  drawing quality" target that weighs every aesthetic equally.
- **`empirical_quality`** — mean of the three metrics that recent
  human-subject work found most predictive of shortest-path task
  accuracy: `node_edge_occlusion`, `edge_crossings`,
  `angular_resolution`. An empirically-weighted alternative to the
  uniform `quality` composite.

When the notebooks talk about "13 metrics", they mean the 11 base
metrics plus these two composites. Some figures show only the 11
(e.g. the duplicate-row diagnostic); most show all 13.

### 5b. Properties dropped from downstream analysis

Of the 24 manifest properties, **seven are dropped** before any
heatmap, clustering, or regression sees them, leaving **17
properties** for analysis:

- **`crossing_number_lb_bipartite`** — only defined on bipartite
  graphs (~80% NaN on this corpus). Imputing it would invent
  structure that isn't there.
- **The six `is_*` binary indicators (`is_planar`, `is_tree`,
  `is_bipartite`, `is_eulerian`, `is_regular`, `is_forest`)** —
  Spearman ρ on a 0/1 column collapses to a rank-biserial
  correlation, which is awkward to read on the same scale as the
  continuous-property ρs (you lose the intuition that `|ρ|` near 1
  means "monotone relationship"). The smaller classes
  (`is_eulerian`, `is_regular`) also produce noisy point estimates
  that distort heatmap colour scales, and standardised β
  coefficients for binary features in OLS aren't comparable with
  those for continuous features. `is_forest` is additionally
  collinear with `is_tree` on this corpus — every graph is
  connected, so forest ⇔ tree. Cohort-level effects of structural
  class are better-shown as group comparisons (left to follow-up
  analyses).

`degree_assortativity` is kept even though it's undefined on the
3.3% of graphs that are regular (zero degree variance → the measure
has no value). Spearman ρ uses pairwise complete cases natively, so
the few NaN rows drop out per correlation without affecting the
rest.

### 5c. Clustering of properties, metrics, and layouts

Three hierarchical clusterings are computed, all with the same
recipe:

1. Compute Spearman ρ on the relevant pairwise comparisons.
2. Convert to distance: `d = 1 − |ρ|`.
3. Run average-linkage hierarchical clustering (`scipy.cluster.hierarchy.linkage`).
4. A slider in the notebook cuts the dendrogram at a chosen
   `|ρ|` threshold, producing the final cluster membership.

The three clusterings are:

- **Property clusters** — pairwise ρ between the 17 structural
  properties (one ρ per pair, across the ~90 k graphs in the
  manifest). Used to group correlated properties (e.g. `n_nodes` /
  `n_edges` / `mean_degree`) in the property × property heatmap
  and the variance-partition columns.
- **Metric clusters** — pairwise ρ between the 11 base metrics
  (across all ~1.5 M drawings). Used to order the rows of the
  metric × metric heatmap. The two composites (`quality`,
  `empirical_quality`) sit detached at the bottom of the dendrogram
  rather than joining a cluster, since they are row-wise means and
  would otherwise be absorbed into whichever cluster they
  correlate with most.
- **Layout clusters** — pairwise ρ between layouts, computed on
  each layout's per-graph `quality` vector. Used to group layouts
  into the empirical families that become the columns of the
  supplementary violin matrix. At the default slider threshold this
  produces seven clusters with descriptive names like
  `Force-directed/Stress/Other`, `Layered/Orthogonal`,
  `MDS/Spectral`, `Baseline (Random)`, `Baseline (Additional)`,
  `Curated`, and `HOLA`.

### 5d. Duplicate-row diagnostic (reported, not applied)

The supplementary analyses report how many drawings share an *exact* 11-metric
vector with at least one other drawing. These rows are **not
removed**: they are different `(graph_id, layout)` pairs that
happened to land in the same place after normalisation. Dropping
them would bias per-layout sample sizes, discard the structural-
saturation signal we want to study, and break the per-graph
envelopes. The duplicate count is reported as a sanity check on
metric resolution.

---

## 6. Caching

The loader writes three parquet files into `.analysis_cache/`:

| File                | What it caches                                              |
| ------------------- | ----------------------------------------------------------- |
| `manifest.parquet`  | The manifest CSV verbatim.                                  |
| `drawings.parquet`  | The merged drawings frame (the output of section 3).        |
| `envelopes.parquet` | The per-graph envelope frame (section 4).                   |

To refresh the cache, set `REFRESH = True` at the top of the
notebook and re-run the loader cell, then flip it back to `False`.
To do it manually, delete the relevant `.parquet` file from
`.analysis_cache/` — the loader will rebuild it on the next run.

The cache is keyed by file path, not by file contents, so if a
metric CSV is added or modified after the cache is written, the
loader will keep returning the stale parquet until the cache is
refreshed.

---