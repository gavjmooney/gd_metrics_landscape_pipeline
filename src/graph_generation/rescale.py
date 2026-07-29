"""Canonical drawing-scale transform — shared by the layout dispatcher,
the retrofit script, and the WSL service.

Every drawing in the corpus is normalised so the axis-aligned bounding
box of the *node positions* has a diagonal of ``TARGET_DIAG`` units,
centred on the origin. Every node is given a radius of
``RADIUS_FRAC * TARGET_DIAG`` (written as yEd-flavoured ``width`` /
``height`` = 2 × radius). Edge bends are scaled in lockstep, then their
direction is flipped if ``bends[0]`` is closer to ``v`` than ``u``
(so ``M(u) → bends → L(v)`` renders as a clean traversal regardless of
how the layout function happened to order its bend samples).

The transform is idempotent: running it on an already-standardised
drawing is a no-op, which lets us call it from both the generator
and the post-hoc patcher without double-scaling.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Mapping, Tuple

TARGET_DIAG = 1000.0
RADIUS_FRAC = 0.0075  # radius = 0.75% of node-bbox diagonal
DIAMETER = 2.0 * RADIUS_FRAC * TARGET_DIAG  # 15.0


Node = object
Pos = Tuple[float, float]


def node_bbox(positions: Mapping[Node, Pos]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in positions.values()]
    ys = [p[1] for p in positions.values()]
    if not xs:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), min(ys), max(xs), max(ys)


def standardise_params(
    positions: Mapping[Node, Pos],
) -> Tuple[float, float, float]:
    """Return ``(cx, cy, scale)`` — the canonical similarity transform.

    ``(cx, cy)`` is the node-bbox centre; ``scale`` maps the node-bbox
    diagonal to ``TARGET_DIAG``. Degenerate inputs (empty, single point,
    coincident nodes — diagonal 0) yield ``scale = 1.0``. The transform
    each consumer applies is ``(x, y) -> ((x - cx) * scale, (y - cy) * scale)``.

    Shared by :func:`standardise` (node positions + polyline bends) and the
    curated edge-geometry transform (``layouts.curated.rescale_paths``) so the
    rescaled edge paths stay locked to the rescaled node positions — both are
    driven by the *same* node-derived centre and scale.
    """
    xmin, ymin, xmax, ymax = node_bbox(positions)
    cx = (xmin + xmax) / 2.0
    cy = (ymin + ymax) / 2.0
    diag = math.hypot(xmax - xmin, ymax - ymin)
    scale = TARGET_DIAG / diag if diag > 0 else 1.0
    return cx, cy, scale


def standardise(
    positions: Mapping[Node, Pos],
    bends: Mapping[Tuple[Node, Node], List[Pos]] | None,
) -> Tuple[Dict[Node, Pos], Dict[Tuple[Node, Node], List[Pos]]]:
    """Return (new_positions, new_bends) at canonical scale + bend direction.

    Both dicts are freshly constructed; inputs are not mutated.
    ``bends`` may be ``None`` or empty — the returned bend dict will
    also be empty in that case.
    """
    if not positions:
        return {}, {}

    cx, cy, scale = standardise_params(positions)

    new_positions: Dict[Node, Pos] = {
        n: ((x - cx) * scale, (y - cy) * scale)
        for n, (x, y) in positions.items()
    }

    new_bends: Dict[Tuple[Node, Node], List[Pos]] = {}
    if bends:
        for (u, v), pts in bends.items():
            if not pts:
                continue
            scaled: List[Pos] = [
                ((float(x) - cx) * scale, (float(y) - cy) * scale)
                for x, y in pts
            ]
            u_xy = new_positions.get(u)
            # Reverse only when the polyline is clearly in v→u order.
            # Earlier we compared d(first, u) vs d(first, v) — but that
            # mis-fires on orthogonal L-shapes where the first bend
            # shares one coord with u yet sits Euclidean-closer to v.
            # Compare first vs last bend's distance to u: if the last
            # bend is closer to u than the first is, the polyline runs
            # v→u and we reverse. Needs at least 2 bends to disambiguate.
            if u_xy is not None and len(scaled) >= 2:
                first, last = scaled[0], scaled[-1]
                d_first_u = (first[0] - u_xy[0]) ** 2 + (first[1] - u_xy[1]) ** 2
                d_last_u = (last[0] - u_xy[0]) ** 2 + (last[1] - u_xy[1]) ** 2
                if d_last_u < d_first_u:
                    scaled.reverse()
            new_bends[(u, v)] = scaled

    return new_positions, new_bends
