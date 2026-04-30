"""IEEE PES power-grid test cases from MATPOWER (.m branch lists)."""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path
from typing import Iterator

import networkx as nx

from .base import Stager, StagedGraph, register_stager

# Each MATPOWER case file with n <= 75 unique buses (cost/reactive variants
# that share topology with another case are excluded — they iso-dedup later).
CASES = [
    ("case4_dist", "case4_dist.m"),
    ("case4gs", "case4gs.m"),
    ("case5", "case5.m"),
    ("case6ww", "case6ww.m"),
    ("case9", "case9.m"),
    ("case10ba", "case10ba.m"),
    ("case11kundur", "case11kundur.m"),
    ("case12da", "case12da.m"),
    ("case14", "case14.m"),
    ("case15da", "case15da.m"),
    ("case15nbr", "case15nbr.m"),
    ("case16am", "case16am.m"),
    ("case16ci", "case16ci.m"),
    ("case17me", "case17me.m"),
    ("case18", "case18.m"),
    ("case18nbr", "case18nbr.m"),
    ("case22", "case22.m"),
    ("case24_ieee_rts", "case24_ieee_rts.m"),
    ("case28da", "case28da.m"),
    ("case30", "case30.m"),
    ("case33bw", "case33bw.m"),
    ("case33mg", "case33mg.m"),
    ("case34sa", "case34sa.m"),
    ("case38si", "case38si.m"),
    ("case39", "case39.m"),
    ("case51ga", "case51ga.m"),
    ("case51he", "case51he.m"),
    ("case57", "case57.m"),
    ("case59", "case59.m"),
    ("case60nordic", "case60nordic.m"),
    ("case69", "case69.m"),
    ("case70da", "case70da.m"),
    ("case74ds", "case74ds.m"),
]
BASE = "https://raw.githubusercontent.com/MATPOWER/matpower/master/data/"

_BRANCH_RE = re.compile(r"mpc\.branch\s*=\s*\[(.*?)\];", re.DOTALL)


def _download_text(url: str, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as r:
        text = r.read().decode("utf-8", errors="replace")
    dst.write_text(text, encoding="utf-8")
    return text


def _extract_edges(mfile_text: str) -> list[tuple[int, int]]:
    m = _BRANCH_RE.search(mfile_text)
    if not m:
        raise ValueError("mpc.branch block not found in .m file")
    edges: list[tuple[int, int]] = []
    for line in m.group(1).splitlines():
        line = line.split("%", 1)[0].strip()
        if not line:
            continue
        tokens = line.rstrip(";").split()
        if len(tokens) < 2:
            continue
        try:
            u, v = int(tokens[0]), int(tokens[1])
        except ValueError:
            continue
        edges.append((u, v))
    return edges


@register_stager
class IEEEPESStager(Stager):
    """MATPOWER-shipped IEEE PES bus topologies (transmission lines as edges)."""

    source_name = "ieee_pes"

    def graphs(self) -> Iterator[StagedGraph]:
        archives_dir = (self.staging_root / "staging" / "_archives"
                        / "ieee_pes")
        for slug, fname in CASES:
            url = BASE + fname
            print(f"fetching {url}", flush=True)
            try:
                m_text = _download_text(url, archives_dir / fname)
            except Exception as e:
                print(f"  skip {slug}: {type(e).__name__}: {e}")
                continue
            try:
                edges = _extract_edges(m_text)
            except Exception as e:
                print(f"  skip {slug}: parse {type(e).__name__}: {e}")
                continue
            G = nx.Graph()
            G.add_edges_from(edges)
            G = nx.convert_node_labels_to_integers(G)
            yield StagedGraph(name=f"ieee_{slug}", graph=G)
