"""SuiteSparse Matrix Collection — small symmetric matrices as graphs."""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Iterator

import networkx as nx
import ssgetpy
from scipy.io import mmread
from tqdm import tqdm

from .base import Stager, StagedGraph, register_stager


def _matrix_to_graph(path: Path) -> nx.Graph:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        M = mmread(str(path))
    G = (nx.from_scipy_sparse_array(M.tocsr()) if hasattr(M, "tocsr")
         else nx.from_numpy_array(M))
    G = nx.Graph(G)
    G.remove_edges_from(nx.selfloop_edges(G))
    G.graph.clear()
    for _, attrs in G.nodes(data=True):
        attrs.clear()
    for _, _, attrs in G.edges(data=True):
        attrs.clear()
    return nx.convert_node_labels_to_integers(G)


@register_stager
class SuiteSparseSmallStager(Stager):
    """Square + structurally symmetric SuiteSparse matrices with n <= 75."""

    source_name = "suitesparse_small"

    def graphs(self) -> Iterator[StagedGraph]:
        print("querying SuiteSparse catalogue ...")
        candidates = ssgetpy.search(
            rowbounds=(2, 75), colbounds=(2, 75), limit=500,
        )
        candidates = [m for m in candidates
                      if m.rows == m.cols and m.nsym == 1.0]
        print(f"  square + symmetric + n <= 75: {len(candidates)} matrices")

        for mat in tqdm(candidates, unit="matrix", desc="suitesparse"):
            try:
                paths = mat.download(format="MM", extract=True)
            except Exception as e:
                print(f"  skip {mat.group}/{mat.name}: download failed "
                      f"({type(e).__name__}: {e})", file=sys.stderr)
                continue

            candidate_files = ([Path(p) for p in paths]
                               if isinstance(paths, (list, tuple))
                               else [Path(paths)])
            mtx_file = None
            for p in candidate_files:
                if p.is_dir():
                    for q in p.glob("*.mtx"):
                        mtx_file = q
                        break
                elif p.suffix == ".mtx":
                    mtx_file = p
                if mtx_file:
                    break
            if mtx_file is None or not mtx_file.exists():
                print(f"  skip {mat.group}/{mat.name}: no .mtx file found",
                      file=sys.stderr)
                continue

            try:
                G = _matrix_to_graph(mtx_file)
            except Exception as e:
                print(f"  skip {mat.group}/{mat.name}: parse failed "
                      f"({type(e).__name__}: {e})", file=sys.stderr)
                continue

            yield StagedGraph(name=f"{mat.group}_{mat.name}", graph=G)
