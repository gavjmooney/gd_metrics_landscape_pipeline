"""gabriel_ratio_nodes — geg.gabriel_ratio_nodes wrapper.

Gabriel Ratio is only well-defined for straight-line drawings, so this
metric assumes every edge is a straight node-point-to-node-point segment:
``geg.gabriel_ratio_nodes`` reads only the node ``x``/``y`` positions and
ignores any edge ``path`` (bend/curve) attributes. It is therefore safe to
apply to every drawing regardless of the layout's actual edge routing.
"""

from __future__ import annotations

import geg

from .base import Metric, MetricContext, register_metric


def _gabriel_ratio_nodes(G, ctx: MetricContext) -> float:
    return float(geg.gabriel_ratio_nodes(G))


METRIC = register_metric(Metric(
    name="gabriel_ratio_nodes", fn=_gabriel_ratio_nodes,
    description="Node-conformance to the Gabriel criterion over straight "
                "node-to-node edges (edge paths ignored).",
))
