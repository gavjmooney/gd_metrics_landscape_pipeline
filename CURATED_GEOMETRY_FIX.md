# Fix: preserve curated edge geometry by staging drawings as GEG (not GraphML)

Instructions for an implementing agent. Read this whole file before editing.
The goal: the `graphs_with_drawings` cohort must keep its curator-authored
**edge geometry** (polyline bends AND Bézier curves) all the way from the
source through to the metrics, so that metrics on curated drawings are computed
on the real curved edges instead of straight chords. The agreed mechanism is to
store these graphs **and** their drawings on disk as `.geg` (JSON) rather than
yEd `.graphml`, because yEd GraphML's `<y:Path>` can only encode polyline bends,
not Bézier curves, and the current writer drops them entirely.

After the fix we will re-run the full pipeline into a fresh output directory.

---

## 1. Background: what is wrong today (verified)

Data flow for a `graphs_with_drawings` graph today:

```
source .geg  --read_geg-->  G (edges carry SVG `path` + `polyline`)
             --write_graphml-->  graphs-with-drawings/<src>/<id>.graphml   <-- geometry LOST here
   layout stage: nx.read_graphml(src) --> curated layout returns (positions, None)
             --geg.write_graphml-->  drawings/curated/.../<id>.graphml      <-- still straight
   metrics stage: geg.read_drawing(.graphml) --> graphml_to_geg --> straight `path`
```

Two independent defects drop the geometry:

1. **Staging loss (gd_collection_v1).** `geg.read_geg` puts edge geometry in the
   edge attribute **`path`** (an SVG string, may include `C`/`Q`/`A` Bézier
   commands). `geg.write_graphml` only serialises bends from an edge's **`bends`**
   attribute and ignores `path` completely. So `read_geg -> write_graphml` writes
   an empty `<y:Path sx="0" sy="0" tx="0" ty="0"/>` for every edge. (geg files:
   `geg/io/geg.py` `read_geg`, `geg/io/graphml.py` `write_graphml`.)

2. **Curated-layout loss (wikipathways).** Even when the staged GraphML *does*
   contain bends (wikipathways stager sets the `bends` attr, which
   `write_graphml` honours), the layout stage reads the source with
   `nx.read_graphml` (`stages/layout.py`, `_run_one`, ~line 196), which does
   **not** recover yEd edge bends — edges come back with empty attrs. The curated
   passthrough layout then returns `bends=None` (`layouts/curated.py` `_curated`),
   so the geometry is dropped before the drawing is written / metrics are run.

Both the in-memory (fused/`write_drawings=false`) and on-disk
(`write_drawings=true`) paths are affected, because the geometry is gone before
either the in-memory metric pass or the disk write happens. Fixing the data flow
fixes both modes; switching the on-disk format to GEG is what makes the saved
artifacts faithful.

### Why GEG and not "fix the GraphML writer"
yEd `<y:PolyLineEdge>` can store polyline bend points but has no representation
for Bézier control points. ~23k edges in gd_collection_v1 use real cubic Béziers
(`C`). GEG stores the raw SVG `path` string, so it round-trips curves losslessly
(`geg.write_geg` / `geg.read_geg` just JSON-serialise the edge attrs). The user
has explicitly accepted that GraphML is not a suitable on-disk format for this
cohort.

---

## 2. Scope: which cohorts are affected (verified against D:\pipeline-output-9)

| source (category `graphs_with_drawings`) | edge geometry in source | status today | needs fix |
|---|---|---|---|
| **gd_collection_v1** | `path` incl. Béziers; 22% of edges bent, 57% of files | LOST at staging | **YES (primary)** |
| **wikipathways** | `bends` on some edges (~30% of files sampled) | survives staging, LOST at curated layout | **YES** |
| **pajek** | none (straight node-to-node edges) | nothing to lose | no (just confirm) |
| **ndex** | none (straight) | nothing to lose | no (just confirm) |
| **TUDataset / COIL-DEL** | none — node x/y only, edges straight | node positions preserved fine | no (just confirm) |

Node positions, shapes, colours are preserved correctly in every cohort
(networkx does parse `<y:Geometry>`); the only loss is **edge routing**. So
COIL-DEL is fine as-is. Still: re-verify each source after the change (see §5),
because the format switch touches all of them.

The pipeline metric functions are already curve-aware: `geg.edge_crossings`,
`geg.node_edge_occlusion`, and `geg.edge_orthogonality` all read the edge `path`
attr (via `_path_or_straight` / `edge_polyline`) and adaptively flatten curves.
They just need to be handed a graph that actually carries the curved `path`.
`gabriel_ratio_nodes` is straight-by-design and is unaffected. (Verified:
`geg.edge_orthogonality`, geg/edge_orthogonality.py, is the "unified definition
that handles straight, polyline, and curved edges" per paper §3.2 eq. 5-6;
`curved_edge_orthogonality` in the same module is **deprecated** — it only emits a
DeprecationWarning and delegates to `edge_orthogonality`. Do **not** switch to it.)

---

## 3. The fix

The cleanest single lever is to make the **filename extension carry the format**:
`graphs_with_drawings` graph_ids end in `.geg`; all other cohorts stay
`.graphml`. Because `graph_id` is used verbatim as the filename in
`resolve_graph_path` / `resolve_drawing_path` (`manifest.py`), this makes every
staged graph and every per-layout drawing for the cohort a `.geg` file
automatically, and lets the readers/writers dispatch on extension.

Make these changes (file references are current as of this writing; confirm by
reading each function before editing):

### 3.1 Stager: write GEG and mint `.geg` graph_ids for the drawing cohort
File: `src/graph_generation/stagers/base.py`

- `_graph_id(self, sg)` (~line 177): the cohort suffix is hard-coded to
  `.graphml`. For `self._preserve_attrs` (i.e. `graphs_with_drawings`) produce
  `f"{safe}_{sg.name}.geg"` instead. Keep `.graphml` for topology cohorts.
- `_write(self, G, path)` (~line 136): for `self._preserve_attrs`, write GEG —
  `geg.write_geg(G, str(path))` — instead of `geg.write_graphml`. Topology
  cohorts keep `nx.write_graphml`. (Equivalently use `geg.write_drawing(G, path)`,
  which already dispatches `.geg -> write_geg`, `.graphml -> write_graphml`.)
- **Normalise geometry to `path` before writing** (important for wikipathways and
  any source that emits `bends`). The metric/reader layer reads the edge **`path`**
  attribute, not `bends`. gd_collection already yields `path`. wikipathways yields
  `bends`. So before writing, ensure each edge has a `path`: if `path` present keep
  it; elif `bends` present synthesise `path = "M{u.x},{u.y} L{b}... L{v.x},{v.y}"`
  and set `polyline=True`; else leave straight (readers synthesise the straight
  chord). `geg.io.convert.graphml_to_geg` shows the exact bends→path synthesis to
  copy. Do this in `_write` (or `_canonicalise`) for the cohort only.

### 3.2 Layout stage: read GEG sources, write GEG drawings
File: `src/graph_generation/stages/layout.py`, function `_run_one`

- Source read (~line 196, `G = nx.read_graphml(src)`): dispatch on extension.
  If `src` ends with `.geg`, read via `geg.read_geg(src)` so node x/y **and**
  edge `path` are loaded; else keep `nx.read_graphml`. (`canonicalise_node_order`
  must still run afterwards — verify it tolerates a read_geg graph; node ids will
  be ints as written by the stager.)
- Drawing write (~lines 266–293, currently `geg.write_graphml(G, tmp)`):
  dispatch on the drawing path's extension. `.geg -> geg.write_geg`,
  `.graphml -> geg.write_graphml`/`nx.write_graphml`. Again `geg.write_drawing`
  does this dispatch for you. Keep the existing `geg.to_svg(...)` render — it
  reads `path` and draws curves, so the verify SVGs will finally show the bends.

### 3.3 Curated passthrough layout: carry the geometry through the rescale
File: `src/graph_generation/layouts/curated.py`, `_curated`

Today it returns `(positions, None)` and the docstring wrongly claims the sources
are straight-edge. The curated drawing must come out in the same normalised frame
as every other layout (so cross-layout metric comparison stays apples-to-apples),
which means the **same similarity transform** `standardise` applies to node
positions (translate by node-bbox centre `(cx,cy)`, scale `TARGET_DIAG/diag`;
see `src/graph_generation/rescale.py`) must also be applied to the edge geometry.

**Approach (decided): preserve curves exactly.** Carry the original SVG `path`
strings through and apply the node-derived affine transform
`(x,y) -> ((x-cx)*scale, (y-cy)*scale)` to **every coordinate** in each path.
Affine transforms preserve Béziers, so control points transform correctly and the
saved drawing stays a faithful curve. Then re-snap each path's endpoints to the
transformed node centres (`geg._paths.snap_path_to_endpoints`) so the stroke
starts/ends exactly on the (rescaled) nodes.

Implementation notes:
- Derive `(cx, cy, scale)` from the **node positions** exactly as
  `rescale.standardise` does (translate by node-bbox centre, scale
  `TARGET_DIAG/diag`, `TARGET_DIAG=1000`), so geometry and nodes stay locked
  together. Reuse/extract that computation rather than recomputing it differently.
- You need a path-coordinate transform helper. geg has `_scale_path`
  (`geg/geg_parser.py`) which scales but does not translate — extend it to apply
  `(coord - c) * scale` per axis, or write a small regex transform over the SVG
  numeric literals. Keep command letters (`M/L/C/Q/S/T/A/H/V/Z`) intact.
- The standard `standardise(positions, bends)` signature only models `positions`
  + polyline `bends`, so curves cannot go through it. Add a dedicated curated
  branch in `_run_one` (or a helper the curated layout calls) that handles the
  `path` transform, instead of routing curves through the `bends` channel.
- Attach the transformed geometry to the in-memory graph as edge `path` (and
  `polyline=True`) so both the in-memory metric pass and the `.geg` write see the
  curved geometry.
- **Do NOT flatten curves to polyline bends.** Flattening would make metrics
  correct but would re-save Béziers as polylines on disk, defeating the move to
  GEG. Keep the raw `path`.

Invariant to preserve: **the edge geometry attached to the graph (as `path`,
`polyline=True`) must be in the same coordinate frame as the rescaled node
positions.** Verify the saved `.geg` has non-straight, node-attached `path`s for
known-curved graphs (see §5).

Also update the misleading docstring/comment in `curated.py` that says the
sources are straight-edge.

### 3.4 Metrics stage: no change needed
`stages/metrics.py` reads drawings via `geg.read_drawing(path)`, which dispatches
`.geg -> read_geg` and yields edges with the curved `path`. The curve-aware
metrics (`edge_crossings`, `node_edge_occlusion`, `edge_orthogonality`) then do
the right thing once the `path` is present — no metric code changes are needed,
and the default `edge_orthogonality` already handles curves (do not use the
deprecated `curved_edge_orthogonality`). Just confirm the stage runs on `.geg`
inputs (it does by design).

### 3.5 Ripple: hard-coded `.graphml` assumptions
Because graph_ids for the cohort now end in `.geg`, grep the repo for code that
assumes a `.graphml` suffix on graph_ids / drawing paths and fix as needed:

```
rg -n "\.graphml" src/ tests/
```

Likely spots to check: dedup/sample audit code, the viewer
(`src/graph_generation/viewer.py`), any `endswith(".graphml")`, and the
`graph_filename` helper in `manifest.py` (that one is for the `generated`
cohort only — leave it). Topology cohorts must keep `.graphml`.

---

## 4. What NOT to change

- **Do not modify the installed `geg` package** (`geg_metrics 0.2.4`) for the core
  fix. `geg.read_geg` / `geg.write_geg` already preserve `path` losslessly; the
  pipeline simply needs to call them. (Optional, separate: `geg.contains_curves` /
  `contains_polylines` in `geg/geg_parser.py` mis-count the `e`/`E` of
  scientific-notation coordinates as curve commands — a latent false-positive bug.
  The pipeline metrics never call these, so it does not affect results; fix
  upstream only if you happen to be touching geg anyway.)
- Do not touch topology cohorts (`generated`, `calibration`, `benchmark`,
  `real_world`) — they have no geometry and stay `.graphml`.
- Do not reuse the ad-hoc `recompute_metrics.py` / `patch_one_colon.py` /
  `metrics_updated/` artifacts in `D:\pipeline-output-9` — they assume the old
  GraphML layout and straight edges. The user's later full re-run will recompute
  metrics fresh from the corrected `.geg` drawings.

---

## 5. Verification — smoke tests only (do NOT run the full pipeline)

**Do not kick off a full pipeline run to verify.** A full run takes up to 48
hours; the user will initiate it themselves once satisfied the issue is resolved.
Convince yourself the fix is correct with fast, narrow smoke tests against a
throwaway output dir and a handful of graphs.

### 5.1 Regression test (add to the suite)
Add a test (e.g. in `tests/test_layouts.py`) that exercises the full data path on
a small synthetic curated graph with one real `C` Bézier-`path` edge, one
multi-`L` polyline edge, and one straight edge:
- Stage it through the cohort `_write`; assert the file is `.geg` and re-reads
  (`geg.read_drawing`) with the curved/polyline `path`s intact.
- Run the curated layout via `_run_one` (writing to a temp `.geg`); assert the
  output re-reads with non-straight `path`s whose endpoints sit on the **rescaled**
  node centres (i.e. geometry is locked to nodes, not left in source coordinates).
- Assert `geg.edge_crossings` / `node_edge_occlusion` / `edge_orthogonality`
  differ between the curved drawing and the same drawing with edges forced
  straight — proving curves actually reach the metrics.

### 5.2 Tiny end-to-end smoke run (throwaway out_dir)
Run the real staging → layout → metrics stages on a *minimal* slice into a temp
`out_dir` — cap `gd_collection_v1` and `wikipathways` to a few graphs each (via
the per-source cap / a cut-down config), `write_drawings = true`, curated layout
only. The gd_collection `.geg` cache under
`D:\pipeline-output-9\staging\_cache\gd-collection-v1` can be reused as input.
This should finish in seconds–minutes, not hours. Then spot-check, using a
known-curved graph such as `GD06_398-410_3` (all edges curved) or
`GD00_259-271_17` (has Béziers):
- Staged: `graphs-with-drawings/gd_collection_v1/<id>.geg` exists; edges have
  multi-command `path`s (count edges whose SVG command set != `[M,L]`, excluding
  the `e` in scientific-notation coordinates).
- Curated drawing: `drawings/curated/graphs_with_drawings/gd_collection_v1/<id>.geg`
  exists and still has non-straight `path`s after the rescale, endpoints on nodes.
- Metric divergence: load the curated `.geg`; compute `edge_crossings` /
  `node_edge_occlusion` / `edge_orthogonality` with curves vs. edges stripped to
  straight chords — they must differ for curved graphs.
- wikipathways: a curved pathway's curated `.geg` retains its bends.
- pajek / ndex / COIL-DEL: drawings still produced; node positions intact; edges
  straight (expected — no regression).

### 5.3 Sanity against the old (broken) output
For the same curved gd_collection graphs, the smoke-run `metrics/curated.csv`
values should differ from `D:\pipeline-output-9\metrics\curated.csv` on the
geometry-sensitive columns (`edge_crossings`, `node_edge_occlusion`,
`crossing_angle`, `angular_resolution`, `edge_orthogonality`); straight graphs
(pajek / ndex / COIL-DEL) should match. This confirms the old run was computing
straight-edge metrics and the fix changes exactly the graphs with curves.

Once these smoke tests pass, hand back to the user — they will start the full run.
