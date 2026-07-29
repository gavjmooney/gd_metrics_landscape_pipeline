"""Stager protocol — per-source download/parse/validate/emit pipeline.

A :class:`Stager` is responsible for one upstream source: it fetches
the raw archive (or queries an API), parses every graph, and the base
class then **canonicalises, filters, computes properties, writes the
graphml, and appends one manifest row per accepted graph** — all in a
single pass. There is no separate "promote" stage; each stager writes
directly to ``graphs/<category>/<source>/`` (or
``graphs-with-drawings/<source>/`` for the drawing cohort).

The base class enforces three filter layers above whatever the stager
yields:

1. **Size** — ``n_min ≤ n ≤ n_max`` mirroring ``[validate]``. The
   Stage stage tightens ``n_min`` to ``[stage].n_min_real_world`` for
   ``real_world`` and ``benchmark`` cohorts (graphs of n ≤ 7 are
   covered by exhaustive_small generation); ``graphs_with_drawings``
   uses ``[validate].n_min`` because we want curator drawings even on
   already-known graphs.
2. **Content** — connected, no zero-edge, density ≤ piecewise cap.
   Equivalent to the old promote ``_classify`` rules; runs before the
   write so we never persist graphs we'd reject.
3. **Cap** — per-source soft ceiling (``[stage.caps]``). The first
   ``max_graphs`` accepted graphs are kept; the rest are silently
   skipped to stop a single dataset from drowning the corpus with
   structurally-similar entries.

The ``graphs_with_drawings`` cohort is written as ``.geg`` (JSON) by the
base :meth:`_write` so curator edge geometry (polyline bends AND Bézier
curves) round-trips losslessly; topology cohorts stay ``.graphml``.
Subclasses with bandwidth-saving metadata pre-filters (NDEx, HoG,
Netzschleuder) read ``self.n_min`` / ``self.n_max`` and reject early.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any, Counter as CounterT, Dict, Iterator, List, Optional, Tuple, Type,
)

import networkx as nx

from ..config import ValidateConfig
from ..manifest import graphs_dir
from ..properties import compute as compute_properties
from ..sources import Source
from ..validation import density_cap_for


@dataclass
class StagedGraph:
    """One graph fresh out of a stager.

    ``upstream_id`` carries provenance (filename, API uuid, etc.) into
    the manifest's ``params_json`` column so each row points back at
    the original upstream entity.
    """
    name: str            # filename stem; no extension, no source prefix
    graph: nx.Graph
    upstream_id: str = ""


@dataclass
class StageResult:
    """What a stager hands back to the parent after its run."""
    source_name: str
    kept: int
    reasons: Dict[str, int]
    manifest_rows: List[Dict[str, Any]]
    timing_rows: List[Dict[str, Any]]
    cap_reached: bool
    elapsed: float


class Stager(ABC):
    """Base class for a per-source stager.

    Subclasses set ``source_name`` (key into the SOURCES registry) and
    implement :meth:`graphs`, yielding :class:`StagedGraph` instances.
    The framework drives :meth:`stage` which applies filters, writes
    each survivor to graphs/<category>/<source>/, and returns rows
    for the manifest + timings sidecars.
    """

    source_name: str = ""

    def __init__(self, source: Source, out_dir: Path,
                 n_min: int = 2, n_max: int = 75,
                 max_graphs: int = 0,
                 validate_config: ValidateConfig | None = None,
                 existing_ids: Optional[set[str]] = None):
        """
        Args:
            source: registry entry for this stager.
            out_dir: corpus output root; per-source dirs hang off
                ``graphs/<category>/<source>/`` (or
                ``graphs-with-drawings/<source>/``).
            n_min, n_max: inclusive node-count bounds.
            max_graphs: per-source soft cap (0 = unlimited).
            validate_config: density / connected / simple rules.
                When None, falls back to permissive defaults.
            existing_ids: graph_ids already in the manifest. Workers
                re-running an idempotent stage skip these without
                re-parsing.
        """
        self.source = source
        self.out_dir = out_dir
        # ``staging_root`` is a back-compat alias kept so the
        # archive-download stagers (TUDataset/Pajek/HoG/etc.) can keep
        # caching upstream tarballs under
        # ``staging/_archives/`` and ``staging/_tudataset_extract/``.
        # The per-graph staging tree (``staging/<source>/<file>.graphml``)
        # is gone — every accepted graph now writes to
        # ``graphs/<category>/<source>/`` directly via
        # :meth:`target_dir`.
        self.staging_root = out_dir
        self.n_min = n_min
        self.n_max = n_max
        self.max_graphs = max_graphs
        self.validate_config = validate_config
        self.existing_ids = existing_ids or set()

    # ------------------------------------------------------------------
    # Subclass surface
    # ------------------------------------------------------------------

    @abstractmethod
    def graphs(self) -> Iterator[StagedGraph]:
        """Yield each parsed graph from the upstream source."""
        ...

    def _write(self, G: nx.Graph, path: Path) -> None:
        """Write one graph file.

        For ``graphs_with_drawings`` we write **GEG** (JSON) via
        :func:`geg.write_geg`, not yEd GraphML. yEd ``<y:Path>`` can only
        encode polyline bends, never Bézier control points, so a GraphML
        round-trip silently drops every curved edge (≈23k cubic-Bézier
        edges in gd_collection alone). GEG stores the raw SVG ``path``
        string, so curves round-trip losslessly. The cohort's graph_ids
        end in ``.geg`` (see :meth:`_graph_id`) so ``path`` already has the
        right extension. Before writing we normalise edge geometry onto the
        ``path`` attribute (see :func:`_ensure_edge_paths`) — the reader /
        metric layer reads ``path``, not yEd ``bends``.

        Topology cohorts (``benchmark`` / ``real_world``) keep plain
        ``nx.write_graphml`` — there's no curator drawing to preserve.
        """
        if self._preserve_attrs:
            import geg
            _ensure_edge_paths(G)
            geg.write_geg(G, str(path))
        else:
            nx.write_graphml(G, path)

    @property
    def _preserve_attrs(self) -> bool:
        """Whether canonicalisation should keep node/edge attrs.

        ``graphs_with_drawings`` keeps them so the curator's x/y/
        colour/shape carry through; topology cohorts strip them so
        the graphml stays minimal.
        """
        return self.source.category == "graphs_with_drawings"

    # ------------------------------------------------------------------
    # Driver
    # ------------------------------------------------------------------

    def target_dir(self) -> Path:
        """Directory under ``out/`` to write accepted graphmls into."""
        return graphs_dir(self.out_dir, self.source.category,
                           self.source.name)

    def _graph_id(self, sg: StagedGraph) -> str:
        """Manifest graph_id for this staged graph.

        Convention: ``<safe_source>_<stem>.graphml`` so the id is
        globally unique and visibly tied to its source. Matches the
        format the previous (stage→promote) pipeline produced, so
        manifests stay drop-in comparable.

        IMPORTANT: ``sg.name`` (the per-graph stem each subclass chooses)
        MUST be stable across runs of the same upstream data — derive it
        from a durable upstream identifier (filename, UUID, indicator
        index) and never from an iteration counter. The stage stage's
        ``existing_ids`` set unions the manifest with the dedup and
        sample audit sidecars; that lookup hits if and only if the
        stem you mint matches the stem the previous run minted.

        The extension carries the on-disk format: ``graphs_with_drawings``
        graphs are stored as ``.geg`` (lossless curved-edge geometry; see
        :meth:`_write`), every topology cohort stays ``.graphml``. Because
        ``graph_id`` is used verbatim as the filename in
        ``resolve_graph_path`` / ``resolve_drawing_path``, this single
        suffix makes the staged graph and every per-layout drawing for the
        cohort a ``.geg`` file automatically, and lets the readers/writers
        dispatch on extension.
        """
        safe = self.source.name.replace("/", "_")
        ext = "geg" if self._preserve_attrs else "graphml"
        return f"{safe}_{sg.name}.{ext}"

    def stage(self) -> StageResult:
        """Run the per-source pass. Returns rows for the parent to
        merge into manifest.csv + _timings/properties.csv.
        """
        target = self.target_dir()
        target.mkdir(parents=True, exist_ok=True)

        kept = 0
        reasons: CounterT[str] = Counter()
        manifest_rows: List[Dict[str, Any]] = []
        timing_rows: List[Dict[str, Any]] = []
        cap_reached = False

        t0 = time.perf_counter()
        for sg in self.graphs():
            graph_id = self._graph_id(sg)

            if graph_id in self.existing_ids:
                reasons["already_in_manifest"] += 1
                continue

            G = self._canonicalise(sg.graph)

            if not self._passes_size(G):
                reasons["out_of_size"] += 1
                continue

            ok, reason = self._passes_content(G)
            if not ok:
                # Strip parameterised tail "(n=14,d=0.531,cap=0.5)" so
                # the funnel summary buckets cleanly.
                reasons[reason.split("(")[0]] += 1
                continue

            try:
                self._write(G, target / graph_id)
            except Exception as e:
                # Malformed upstream attribute (e.g. 1-coord bend) —
                # skip rather than crash the whole worker.
                partial = target / graph_id
                if partial.exists():
                    try:
                        partial.unlink()
                    except OSError:
                        pass
                reasons[f"write_failed:{type(e).__name__}"] += 1
                continue

            props, timings = compute_properties(G, return_timings=True)
            manifest_rows.append({
                "graph_id": graph_id,
                "generator": self.source.name,
                "category": self.source.category,
                "source": self.source.name,
                "seed": 0,
                "params_json": _json_compact({
                    "upstream": sg.upstream_id or sg.name,
                }),
                **props,
            })
            timing_rows.append({
                "graph_id": graph_id,
                "n_nodes": props.get("n_nodes"),
                "n_edges": props.get("n_edges"),
                "timings": timings,
            })

            kept += 1
            if self.max_graphs and kept >= self.max_graphs:
                cap_reached = True
                break

        elapsed = time.perf_counter() - t0
        cap_note = "  (cap reached)" if cap_reached else ""
        print(f"[{self.source.name}] kept={kept:,}  "
              f"reasons={dict(reasons.most_common(5))}  "
              f"n_min={self.n_min} n_max={self.n_max} "
              f"cap={self.max_graphs or 'none'}{cap_note}",
              flush=True)

        return StageResult(
            source_name=self.source.name, kept=kept, reasons=dict(reasons),
            manifest_rows=manifest_rows, timing_rows=timing_rows,
            cap_reached=cap_reached, elapsed=elapsed,
        )

    # ------------------------------------------------------------------
    # Filters / coercion shared by every stager
    # ------------------------------------------------------------------

    def _canonicalise(self, G: nx.Graph) -> nx.Graph:
        """Coerce to simple undirected Graph with no self-loops.

        For topology cohorts (real_world / benchmark / calibration)
        all node and edge attrs are stripped — the manifest and
        topology graphml carry only what subsequent stages need.

        For ``graphs_with_drawings`` the attrs are kept (renumbered
        node ids carry an ``orig_id`` back-pointer) so the curator's
        layout hints survive.
        """
        if G.is_directed():
            G = G.to_undirected(as_view=False)
        if G.is_multigraph():
            G = nx.Graph(G)
        sl = list(nx.selfloop_edges(G))
        if sl:
            G.remove_edges_from(sl)

        if not self._preserve_attrs:
            G.graph.clear()
            for _, attrs in G.nodes(data=True):
                attrs.clear()
            for _, _, attrs in G.edges(data=True):
                attrs.clear()
            return nx.convert_node_labels_to_integers(G)

        G.graph.clear()
        mapping = {old: i for i, old in enumerate(sorted(G.nodes, key=str))}
        H = nx.Graph()
        for old, new in mapping.items():
            attrs = dict(G.nodes[old])
            H.add_node(new, orig_id=str(old), **attrs)
        for u, v, data in G.edges(data=True):
            H.add_edge(mapping[u], mapping[v], **data)
        return H

    def _passes_size(self, G: nx.Graph) -> bool:
        n = G.number_of_nodes()
        return self.n_min <= n <= self.n_max

    def _passes_content(self, G: nx.Graph) -> Tuple[bool, str]:
        """Connected + density check (size handled separately).

        Mirrors the old promote ``_classify`` rules; the per-cohort
        size floor is applied via ``self.n_min`` from
        :func:`graph_generation.stages.stage._bounds_for`.
        """
        if G.number_of_edges() == 0:
            return False, "no_edges"
        vc = self.validate_config
        if vc is None or vc.require_connected:
            if not nx.is_connected(G):
                return False, "disconnected"
        if vc is not None:
            cap = density_cap_for(G.number_of_nodes(), vc.density_cap)
            d = nx.density(G)
            if d > cap:
                return False, f"over_density_cap(n={G.number_of_nodes()},d={d:.3f},cap={cap:.2f})"
        return True, ""


def _ensure_edge_paths(G: nx.Graph) -> None:
    """Normalise curator edge geometry onto the ``path`` attribute, in place.

    The reader / metric layer reads each edge's SVG ``path`` string, not yEd
    ``bends``. Sources differ in what they emit:

    - **gd_collection** already yields ``path`` (with cubic Béziers) plus a
      correct ``polyline`` flag — left untouched.
    - **wikipathways** yields intermediate ``bends`` and no ``path`` — we
      synthesise ``path = "M{u} L{bend}… L{v}"`` (mirroring
      ``geg.io.convert.graphml_to_geg``), set ``polyline=True``, and drop the
      now-redundant ``bends`` so the stale source-coordinate bends don't ride
      along into the ``.geg``.
    - **straight edges** (neither ``path`` nor ``bends``) are left without a
      ``path`` — readers and ``to_svg`` synthesise the straight node-to-node
      chord on demand.
    """
    for u, v, attrs in G.edges(data=True):
        if attrs.get("path"):
            continue
        bends = attrs.get("bends")
        if not bends:
            continue
        try:
            ux, uy = float(G.nodes[u]["x"]), float(G.nodes[u]["y"])
            vx, vy = float(G.nodes[v]["x"]), float(G.nodes[v]["y"])
        except (KeyError, TypeError, ValueError):
            continue
        segs = [f"M{ux},{uy}"]
        segs += [f"L{float(bx)},{float(by)}" for bx, by in bends]
        segs.append(f"L{vx},{vy}")
        attrs["path"] = " ".join(segs)
        attrs["polyline"] = True
        attrs.pop("bends", None)


def _json_compact(d: Dict[str, Any]) -> str:
    import json
    return json.dumps(d, separators=(",", ":"), sort_keys=True)


STAGER_REGISTRY: Dict[str, Type[Stager]] = {}


def register_stager(cls: Type[Stager]) -> Type[Stager]:
    if not getattr(cls, "source_name", ""):
        raise ValueError(f"stager {cls.__name__} must set 'source_name'")
    if cls.source_name in STAGER_REGISTRY:
        raise ValueError(f"duplicate stager source_name: {cls.source_name}")
    STAGER_REGISTRY[cls.source_name] = cls
    return cls


def stager_for(source: Source, out_dir: Path,
               n_min: int = 2, n_max: int = 75,
               max_graphs: int = 0,
               validate_config: ValidateConfig | None = None,
               existing_ids: Optional[set[str]] = None) -> Stager:
    """Instantiate the right stager class for a source.

    Registry indexes by exact ``source.name`` first; the parametric
    TUDataset stager registers under the prefix ``"TUDataset/"`` and
    matches any ``TUDataset/<NAME>``.
    """
    kwargs = dict(
        n_min=n_min, n_max=n_max, max_graphs=max_graphs,
        validate_config=validate_config, existing_ids=existing_ids,
    )
    if source.name in STAGER_REGISTRY:
        return STAGER_REGISTRY[source.name](source, out_dir, **kwargs)
    for key in STAGER_REGISTRY:
        if key.endswith("/") and source.name.startswith(key):
            return STAGER_REGISTRY[key](source, out_dir, **kwargs)
    raise KeyError(f"no stager registered for source {source.name!r}")
