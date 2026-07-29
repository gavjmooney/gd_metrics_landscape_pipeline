"""Rebuild ``analysis/data/sankey_overview.json`` for ``sankey_pipeline.py``.

Derives every count the Sankey diagram needs from a pipeline run:

- final corpus + per-source breakdown  → ``<data>/manifest.csv``
- drawings per layout                  → ``<data>/metrics/*.csv`` row counts
- pre-sample (staged) counts           → final manifest rows plus the rows
  recorded as dropped in ``manifest.sampling-audit.csv`` and
  ``manifest.dedup-audit.csv``
- stage-time filter losses             → ``reasons={...}`` lines in ``run.log``

The audit CSVs and ``run.log`` live in the full pipeline output directory
(not shipped with the repo); pass it via ``--run-dir``. The manifest and
metric CSVs default to ``analysis/data``.

Usage:
    python rebuild_sankey_overview.py --run-dir /path/to/pipeline-output
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent

METRICS = [
    "angular_resolution",
    "aspect_ratio",
    "crossing_angle",
    "edge_crossings",
    "edge_length_deviation",
    "edge_orthogonality",
    "kruskal_stress",
    "neighbourhood_preservation",
    "node_edge_occlusion",
    "node_resolution",
    "node_uniformity",
]


def effective_source(row) -> str:
    """Manifest ``source`` when set, else ``generator`` (generated and
    calibration graphs carry no source)."""
    src = row["source"]
    if isinstance(src, str) and src:
        return src
    gen = row["generator"]
    return gen if isinstance(gen, str) else ""


def attribute_dropped(graph_id: str, source: str, known_sources: list[str]) -> str:
    """Source for an audit row: the recorded source when present, else the
    longest known source/generator prefix of the graph_id (generated and
    calibration audit rows have an empty source column)."""
    if isinstance(source, str) and source:
        return source
    candidates = [s for s in known_sources if graph_id.startswith(s + "_")]
    if not candidates:
        return "unknown"
    return max(candidates, key=len)


def parse_filter_totals(run_log: Path) -> dict[str, int]:
    """Sum per-source ``reasons={...}`` dicts from the stage step's log
    lines, keeping only the LAST line per source (resumed runs repeat)."""
    pat = re.compile(r"^\[([^\]]+)\] kept=[\d,]+\s+reasons=(\{[^}]*\})")
    per_source: dict[str, dict[str, int]] = {}
    with open(run_log, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = pat.match(line)
            if m:
                per_source[m.group(1)] = ast.literal_eval(m.group(2))
    totals: dict[str, int] = {}
    for reasons in per_source.values():
        for reason, n in reasons.items():
            totals[reason] = totals.get(reason, 0) + int(n)
    return totals


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, type=Path,
                    help="Full pipeline output dir (audit CSVs + run.log)")
    ap.add_argument("--data-dir", type=Path, default=HERE / "data",
                    help="Analysis data dir (manifest.csv + metrics/)")
    args = ap.parse_args()

    manifest = pd.read_csv(
        args.data_dir / "manifest.csv",
        usecols=["graph_id", "category", "source", "generator"],
    )
    manifest["eff_source"] = manifest.apply(effective_source, axis=1)
    src_to_cat = (
        manifest.groupby("eff_source")["category"].first().to_dict()
    )
    known_sources = sorted(src_to_cat, key=len, reverse=True)

    # --- rows dropped between staging and the final manifest -------------
    parts = [manifest[["graph_id", "category", "eff_source"]]]

    samp = pd.read_csv(args.run_dir / "manifest.sampling-audit.csv")
    samp["eff_source"] = [
        attribute_dropped(g, s, known_sources)
        for g, s in zip(samp["dropped_graph_id"], samp["source"])
    ]
    samp["category"] = samp["eff_source"].map(src_to_cat).fillna("real_world")
    parts.append(samp.rename(columns={"dropped_graph_id": "graph_id"})[
        ["graph_id", "category", "eff_source"]
    ])

    dedup = pd.read_csv(args.run_dir / "manifest.dedup-audit.csv")
    dedup["eff_source"] = [
        attribute_dropped(g, s, known_sources)
        for g, s in zip(dedup["dropped_graph_id"], dedup["dropped_source"])
    ]
    dedup["category"] = dedup["dropped_category"]
    parts.append(dedup.rename(columns={"dropped_graph_id": "graph_id"})[
        ["graph_id", "category", "eff_source"]
    ])

    pre_sample = pd.concat(parts, ignore_index=True)
    per_cohort = pre_sample["category"].value_counts().to_dict()
    per_cohort_source = [
        {"category": cat, "source": src, "count": int(n)}
        for (cat, src), n in (
            pre_sample.groupby(["category", "eff_source"]).size().items()
        )
    ]

    # --- drawings per layout --------------------------------------------
    per_layout: dict[str, int] = {}
    for csv_path in sorted((args.data_dir / "metrics").glob("*.csv")):
        with open(csv_path, encoding="utf-8") as fh:
            per_layout[csv_path.stem] = sum(1 for _ in fh) - 1

    summary = {
        "pre_sample_manifest": {
            "total": int(len(pre_sample)),
            "per_cohort": {k: int(v) for k, v in per_cohort.items()},
            "per_cohort_source": per_cohort_source,
        },
        "stages": {
            "stage": {"filter_totals": parse_filter_totals(args.run_dir / "run.log")},
            "sample": {"after": int(len(pre_sample) - len(samp))},
            "dedup": {"after": int(len(manifest))},
        },
        "drawings": {
            "per_layout": per_layout,
            "total": int(sum(per_layout.values())),
        },
        "metrics": METRICS,
    }

    out = args.data_dir / "sankey_overview.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    print(f"  staged={summary['pre_sample_manifest']['total']:,}  "
          f"sampled={summary['stages']['sample']['after']:,}  "
          f"deduped={summary['stages']['dedup']['after']:,}  "
          f"drawings={summary['drawings']['total']:,}  "
          f"layouts={len(per_layout)}")


if __name__ == "__main__":
    main()
