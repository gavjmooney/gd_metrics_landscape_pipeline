"""Build a single-page HTML viewer for verify-sample SVGs.

Walks ``<out_dir>/drawings/<algo>/<category>/<source>/<graph_id>.svg``
(plus the flat ``calibration`` and ``generated`` cohorts) and writes
``<out_dir>/viewer.html`` — a self-contained page that loads each SVG
lazily and offers client-side filters by layout / cohort / source /
graph_id.

Two entry points:
  - :func:`build` — used by the layout stage to auto-emit the viewer
    after every layout subprocess finishes.
  - ``tools/build_viewer.py`` — thin CLI wrapper for manual rebuilds.
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import List


# Cohort dirs that hold ``drawings/<algo>/<cat>/<src>/<gid>.svg``.
_NESTED_COHORTS = {"benchmark", "real_world", "graphs_with_drawings"}


def scan(drawings_root: Path) -> List[dict]:
    """Walk drawings/ and return one record per SVG.

    Each record: ``{layout, category, source, graph_id, svg}``.
    The ``svg`` path is relative to ``drawings_root.parent`` so the
    HTML works over file:// regardless of where the page lives.
    """
    out: list[dict] = []
    if not drawings_root.is_dir():
        return out
    for layout_dir in sorted(drawings_root.iterdir()):
        if not layout_dir.is_dir():
            continue
        layout = layout_dir.name
        for cat_dir in sorted(layout_dir.iterdir()):
            if not cat_dir.is_dir():
                continue
            cat = cat_dir.name
            if cat in _NESTED_COHORTS:
                # one extra level: <source>/
                for src_dir in sorted(cat_dir.iterdir()):
                    if not src_dir.is_dir():
                        continue
                    src = src_dir.name
                    for svg in sorted(src_dir.glob("*.svg")):
                        out.append(_record(svg, drawings_root,
                                            layout, cat, src))
            else:
                # flat: <gid>.svg directly under category dir
                for svg in sorted(cat_dir.glob("*.svg")):
                    out.append(_record(svg, drawings_root,
                                        layout, cat, ""))
    return out


def _record(svg_path: Path, drawings_root: Path,
             layout: str, cat: str, source: str) -> dict:
    rel = svg_path.relative_to(drawings_root.parent).as_posix()
    return {
        "layout": layout,
        "category": cat,
        "source": source,
        "graph_id": svg_path.stem,
        "svg": rel,
    }


def render(records: List[dict], thumb_size: int = 220) -> str:
    """Build the self-contained HTML."""
    layouts = sorted({r["layout"] for r in records})
    categories = sorted({r["category"] for r in records})
    sources = sorted({r["source"] for r in records if r["source"]})
    n = len(records)

    title = f"Pipeline drawings ({n:,} SVGs)"
    payload = json.dumps(records, separators=(",", ":"))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{escape(title)}</title>
<style>
  :root {{
    --thumb: {thumb_size}px;
  }}
  body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont,
                                    "Segoe UI", Roboto, sans-serif;
         color: #222; background: #fafafa; }}
  header {{ padding: 1rem 1.5rem; background: #fff;
            border-bottom: 1px solid #e0e0e0;
            position: sticky; top: 0; z-index: 5;
            display: flex; flex-wrap: wrap; gap: 0.75rem;
            align-items: baseline; }}
  header h1 {{ font-size: 1.1rem; margin: 0 1rem 0 0; font-weight: 600; }}
  header label {{ font-size: 0.85rem; color: #555; }}
  header select, header input {{
    font-size: 0.9rem; padding: 0.25rem 0.5rem;
    border: 1px solid #ccc; border-radius: 4px;
  }}
  header input {{ width: 220px; }}
  #count {{ margin-left: auto; font-size: 0.9rem; color: #777; }}
  main {{ display: grid;
          grid-template-columns: repeat(auto-fill, var(--thumb));
          gap: 1rem; padding: 1rem; }}
  .card {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 6px;
           overflow: hidden; }}
  .card .meta {{ padding: 0.4rem 0.6rem; font-size: 0.75rem; color: #555;
                 border-bottom: 1px solid #f0f0f0;
                 white-space: nowrap; overflow: hidden;
                 text-overflow: ellipsis; }}
  .card .meta .layout {{ font-weight: 600; color: #333; }}
  .card .meta .gid    {{ display: block; color: #888;
                          font-family: ui-monospace, monospace;
                          font-size: 0.7rem; }}
  .card object {{ width: 100%; height: var(--thumb); display: block;
                  background: #fff; }}
  .hide {{ display: none !important; }}
</style>
</head>
<body>
<header>
  <h1>{escape(title)}</h1>
  <label>layout
    <select id="f-layout"><option value="">all ({len(layouts)})</option>
    {''.join(f'<option>{escape(x)}</option>' for x in layouts)}
    </select>
  </label>
  <label>cohort
    <select id="f-cat"><option value="">all</option>
    {''.join(f'<option>{escape(x)}</option>' for x in categories)}
    </select>
  </label>
  <label>source
    <select id="f-src"><option value="">all</option>
    {''.join(f'<option>{escape(x)}</option>' for x in sources)}
    </select>
  </label>
  <label>graph_id
    <input id="f-gid" type="search" placeholder="substring filter">
  </label>
  <span id="count">{n:,} drawings</span>
</header>
<main id="grid"></main>
<script>
const RECORDS = {payload};
const grid = document.getElementById('grid');
const fLayout = document.getElementById('f-layout');
const fCat    = document.getElementById('f-cat');
const fSrc    = document.getElementById('f-src');
const fGid    = document.getElementById('f-gid');
const counter = document.getElementById('count');

function makeCard(r) {{
  const div = document.createElement('div');
  div.className = 'card';
  div.dataset.layout = r.layout;
  div.dataset.cat = r.category;
  div.dataset.src = r.source;
  div.dataset.gid = r.graph_id;
  div.innerHTML = `<div class="meta">
    <span class="layout">${{r.layout}}</span> · ${{r.category}}${{r.source ? ' / ' + r.source : ''}}
    <span class="gid">${{r.graph_id}}</span>
  </div>
  <object type="image/svg+xml" data-src="${{r.svg}}"></object>`;
  return div;
}}

const cards = RECORDS.map(makeCard);
cards.forEach(c => grid.appendChild(c));

// Lazy-load SVGs as cards scroll into view.
const io = new IntersectionObserver(es => {{
  for (const e of es) {{
    if (!e.isIntersecting) continue;
    const obj = e.target.querySelector('object');
    if (obj && obj.dataset.src) {{
      obj.data = obj.dataset.src;
      delete obj.dataset.src;
    }}
    io.unobserve(e.target);
  }}
}}, {{rootMargin: '500px'}});
cards.forEach(c => io.observe(c));

function applyFilter() {{
  const layout = fLayout.value;
  const cat    = fCat.value;
  const src    = fSrc.value;
  const gid    = fGid.value.trim().toLowerCase();
  let n = 0;
  for (const c of cards) {{
    const ok = (!layout || c.dataset.layout === layout)
            && (!cat    || c.dataset.cat    === cat)
            && (!src    || c.dataset.src    === src)
            && (!gid    || c.dataset.gid.toLowerCase().includes(gid));
    c.classList.toggle('hide', !ok);
    if (ok) n += 1;
  }}
  counter.textContent = n.toLocaleString() + ' drawings';
}}
[fLayout, fCat, fSrc, fGid].forEach(el =>
  el.addEventListener('input', applyFilter));
</script>
</body>
</html>
"""


def build(out_dir: Path, html_path: Path | None = None,
          thumb_size: int = 220) -> tuple[int, Path]:
    """Build the viewer HTML for one corpus output dir.

    Returns ``(n_records, html_path)``. Idempotent — overwrites
    ``viewer.html`` with the current state of ``drawings/``.
    Skips silently if no SVGs are present.
    """
    drawings_root = out_dir / "drawings"
    target = html_path or out_dir / "viewer.html"
    records = scan(drawings_root)
    if not records:
        return 0, target
    target.write_text(render(records, thumb_size), encoding="utf-8")
    return len(records), target
