"""NDEx Network Data Exchange — networks with curator-saved layouts.

Licence policy: stage only networks whose CX ``rights`` field matches an
unambiguously-open licence per the Open Definition
(https://opendefinition.org/) — CC0, CC BY, CC BY-SA, public domain,
or an OSI-approved permissive software licence. Networks with no
declared rights are *rejected* (we cannot assume permissive); networks
with non-commercial or no-derivatives clauses are *rejected* (those
are not "open" per the Open Definition even though academic use may
be tolerated).

The rights string lives in the CX networkAttributes aspect (only
populated in the per-network detail JSON, not in the search payload),
so the licence check runs after fetching the full document.
"""

from __future__ import annotations

import csv
import json
import urllib.request
from pathlib import Path
from typing import Iterator

import networkx as nx

from .base import Stager, StagedGraph, register_stager

SEARCH_URL = "https://www.ndexbio.org/v2/search/network"
NETWORK_URL = "https://www.ndexbio.org/v2/network/{uuid}"

# Match patterns that unambiguously indicate an open-data licence.
# Lower-case, substring match. Order doesn't matter; first hit wins.
OPEN_LICENCE_PATTERNS = (
    # Public-domain dedications
    "cc0", "cc-0", "public domain", "public-domain", "waiver",
    # CC BY (Attribution) — long form and short form, multiple versions
    "attribution 4.0 international", "attribution 3.0",
    "cc by 4.0", "cc by 3.0", "cc-by-4.0", "cc-by-3.0",
    "creativecommons.org/licenses/by/",
    # CC BY-SA (Attribution-ShareAlike) — open per Open Definition
    "attribution-sharealike", "cc by-sa", "cc-by-sa",
    "creativecommons.org/licenses/by-sa/",
    # OSI-approved permissive software licences sometimes used for data
    "mit license", "apache license", "apache 2.0", "bsd license",
)

# Markers that disqualify a licence even if it would otherwise match
# above (e.g. "CC BY-NC 4.0" contains "cc by" as a prefix). Checked
# before the positive list.
RESTRICTIVE_MARKERS = (
    "noncommercial", "non-commercial", "non commercial",
    "noderivatives", "no derivatives", "noderivative",
    "/by-nc/", "/by-nd/", "-nc-", "-nd-",
    " nc ", " nd ",
)

# Vary the search query to broaden the pool — NDEx pagination is per-query.
_SEARCH_QUERIES = [
    "*", "signaling", "pathway", "interaction", "cancer", "protein",
    "network", "genes", "metabolism", "expression", "biological", "graph",
]
DEFAULT_LIMIT = 200
DEFAULT_MAX_PAGES = 50


def _post_json(url: str, body: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "User-Agent": "graph_generation"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "graph_generation"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))


def _search_page(offset: int, size: int = 100,
                 search_string: str = "*") -> list[dict]:
    doc = _post_json(
        f"{SEARCH_URL}?size={size}&offset={offset}",
        {"searchString": search_string},
    )
    return doc.get("networks", [])


def _rights_from_cx(doc: list) -> tuple[str, str]:
    """Return ``(rights, rights_holder)`` from a CX document.

    Both come from the ``networkAttributes`` aspect — the search-time
    payload does not carry these, only the per-network detail JSON
    does. Empty strings if missing.
    """
    rights = rights_holder = ""
    for aspect in doc:
        if not isinstance(aspect, dict):
            continue
        for a in aspect.get("networkAttributes", []) or []:
            name = (a.get("n") or "").strip().lower()
            value = str(a.get("v") or "").strip()
            if name == "rights" and not rights:
                rights = value
            elif name == "rightsholder" and not rights_holder:
                rights_holder = value
    return rights, rights_holder


def _is_open(rights: str) -> bool:
    """True iff ``rights`` is unambiguously open per the Open Definition.

    Empty / missing is treated as NOT open (we cannot assume
    permissive). Restrictive markers (NC, ND) disqualify even
    otherwise-matching strings.
    """
    if not rights:
        return False
    low = rights.lower()
    if any(m in low for m in RESTRICTIVE_MARKERS):
        return False
    return any(p in low for p in OPEN_LICENCE_PATTERNS)


def _parse_cx_any(doc: list) -> nx.Graph | None:
    """Build a graph with x/y from a CX1 or CX2 NDEx document."""
    node_pos: dict[int, tuple[float, float]] = {}
    edges: list[tuple[int, int]] = []
    for aspect in doc:
        if not isinstance(aspect, dict):
            continue
        if "nodes" in aspect:
            for n in aspect["nodes"]:
                nid_raw = n.get("id") if "id" in n else n.get("@id")
                if nid_raw is None:
                    continue
                try:
                    nid = int(nid_raw)
                except (TypeError, ValueError):
                    continue
                x, y = n.get("x"), n.get("y")
                if x is not None and y is not None:
                    try:
                        node_pos[nid] = (float(x), float(y))
                    except (TypeError, ValueError):
                        pass
        if "cartesianLayout" in aspect:
            for p in aspect["cartesianLayout"]:
                nid_raw = p.get("node")
                if nid_raw is None:
                    continue
                try:
                    nid = int(nid_raw)
                    x = float(p["x"])
                    y = float(p["y"])
                except (KeyError, TypeError, ValueError):
                    continue
                node_pos[nid] = (x, y)
        if "edges" in aspect:
            for e in aspect["edges"]:
                try:
                    s = int(e["s"])
                    t = int(e["t"])
                except (KeyError, TypeError, ValueError):
                    continue
                edges.append((s, t))
    if not node_pos:
        return None
    G = nx.Graph()
    for nid, (x, y) in node_pos.items():
        G.add_node(nid, x=x, y=y)
    for s, t in edges:
        if s in node_pos and t in node_pos and s != t:
            G.add_edge(s, t)
    if G.number_of_edges() == 0:
        return None
    mapping = {old: i for i, old in enumerate(sorted(G.nodes))}
    H = nx.Graph()
    for old, new in mapping.items():
        H.add_node(new, x=G.nodes[old]["x"], y=G.nodes[old]["y"])
    for u, v in G.edges:
        H.add_edge(mapping[u], mapping[v])
    return H


@register_stager
class NDExStager(Stager):
    """NDEx networks with hasLayout=true, permissive licence, 2 <= n <= 75."""

    source_name = "ndex"

    def graphs(self) -> Iterator[StagedGraph]:
        """Yield NDEx networks with hasLayout=true, sized in-bounds, and
        carrying an unambiguously open licence.

        Funnel: hasLayout → size (per-stager, set by Stage stage) →
        per-network detail fetch → rights check (open?) → CX parse.
        Each rejection reason is logged in
        ``staging-graphs-with-drawings/ndex/_licence_audit.csv`` so
        the policy can be reviewed and edge cases revisited.
        """
        seen_uuids: set[str] = set()
        n_parsed = 0
        funnel = {"no_layout": 0, "out_of_size": 0, "fetch_fail": 0,
                  "no_rights": 0, "restrictive": 0, "open": 0,
                  "parse_fail": 0}
        audit_rows: list[dict] = []

        search_iter = []
        for q in _SEARCH_QUERIES:
            for page in range(DEFAULT_MAX_PAGES):
                search_iter.append((q, page * 100))

        for query, offset in search_iter:
            if n_parsed >= DEFAULT_LIMIT:
                break
            try:
                networks = _search_page(offset, size=100, search_string=query)
            except Exception as e:
                print(f"  search {query!r}@{offset} failed: "
                      f"{type(e).__name__}: {e}")
                continue
            if not networks:
                continue
            for net in networks:
                if n_parsed >= DEFAULT_LIMIT:
                    break
                if not net.get("hasLayout"):
                    funnel["no_layout"] += 1
                    continue
                n = int(net.get("nodeCount") or 0)
                if n < self.n_min or n > self.n_max:
                    funnel["out_of_size"] += 1
                    continue
                uuid = net["externalId"]
                if uuid in seen_uuids:
                    continue
                seen_uuids.add(uuid)
                name = net.get("name") or uuid
                try:
                    doc = _get_json(NETWORK_URL.format(uuid=uuid))
                except Exception as e:
                    funnel["fetch_fail"] += 1
                    print(f"  {uuid}: download failed "
                          f"({type(e).__name__}: {e})")
                    continue
                rights, rights_holder = _rights_from_cx(doc)
                # Licence gate — strict, fails closed.
                if not rights:
                    funnel["no_rights"] += 1
                    audit_rows.append({"uuid": uuid, "name": name,
                                        "rights": "", "rights_holder": rights_holder,
                                        "decision": "rejected:no_rights"})
                    continue
                if not _is_open(rights):
                    funnel["restrictive"] += 1
                    audit_rows.append({"uuid": uuid, "name": name,
                                        "rights": rights, "rights_holder": rights_holder,
                                        "decision": "rejected:not_open"})
                    continue
                G = _parse_cx_any(doc)
                if G is None:
                    funnel["parse_fail"] += 1
                    continue
                funnel["open"] += 1
                audit_rows.append({"uuid": uuid, "name": name,
                                    "rights": rights, "rights_holder": rights_holder,
                                    "decision": "kept"})
                slug_name = "".join(
                    c if c.isalnum() or c in "-_" else "_" for c in name
                )[:40]
                # Stem must be stable across runs so the manifest's
                # existing_ids skip works on re-stage. UUID is the
                # durable upstream key; the slug is decoration. Earlier
                # versions prefixed an ``n_parsed`` counter which made
                # the stem depend on iteration order — that re-staged
                # every NDEx network on every re-run because the
                # counter assigned different positions to the same UUID
                # depending on the search-API response order.
                stem = f"ndex_{slug_name}_{uuid}"
                yield StagedGraph(name=stem, graph=G, upstream_id=uuid)
                n_parsed += 1

        print(f"\n[ndex] funnel: " + "  ".join(
            f"{k}={v}" for k, v in funnel.items()))
        self._write_audit(audit_rows)

    def _write_audit(self, rows: list[dict]) -> None:
        if not rows:
            return
        out = self.target_dir()
        out.mkdir(parents=True, exist_ok=True)
        path = out / "_licence_audit.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["uuid", "name", "rights",
                               "rights_holder", "decision"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"[ndex] licence audit -> {path.name} "
              f"({len(rows)} networks reviewed)")
