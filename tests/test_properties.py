"""Pinned regression on the analytic crossing-number lower bounds.

The audit that motivated the reproducibility refactor noticed
``crossing_number_lb_bipartite`` mean shifting between two pipeline
runs whose seeds and code were notionally identical. The shift turned
out to be corpus-mix-driven (more bipartite graphs in the second run
shifted the average) rather than a formula change, but the formula is
now pinned on hand-computed examples so any future edit to either the
local override (`graph_generation.properties.crossing_number_lb_bipartite`)
or geg's upstream version surfaces as an explicit test failure.
"""

from __future__ import annotations

import math

import networkx as nx

from graph_generation.properties import (
    crossing_number_lb_bipartite,
    crossing_number_lb_euler,
)


def test_bipartite_lb_K_3_3_is_one():
    """K_{3,3}: n=6, m=9, bound = max(0, 9 - (2*6 - 4)) = 1.
    The known crossing number of K_{3,3} is 1, so the bound is tight."""
    G = nx.complete_bipartite_graph(3, 3)
    assert crossing_number_lb_bipartite(G) == 1


def test_bipartite_lb_K_4_4_is_four():
    """K_{4,4}: n=8, m=16, bound = max(0, 16 - 12) = 4.
    Known cr(K_{4,4}) = 4, again tight."""
    G = nx.complete_bipartite_graph(4, 4)
    assert crossing_number_lb_bipartite(G) == 4


def test_bipartite_lb_K_5_5_is_nine():
    """K_{5,5}: n=10, m=25, bound = max(0, 25 - 16) = 9.
    Known cr(K_{5,5}) = 16, so the bound is valid but not tight."""
    G = nx.complete_bipartite_graph(5, 5)
    assert crossing_number_lb_bipartite(G) == 9


def test_bipartite_lb_C_4_is_zero():
    """C_4 is bipartite and planar — bound is 0, not NaN."""
    G = nx.cycle_graph(4)
    assert crossing_number_lb_bipartite(G) == 0


def test_bipartite_lb_K_4_is_nan_not_zero():
    """K_4 is non-bipartite (has triangles) — formula returns NaN so
    callers can fall back to the generic Euler bound. A regression
    that returned 0 here would silently bias bipartite-cohort
    statistics."""
    G = nx.complete_graph(4)
    assert math.isnan(crossing_number_lb_bipartite(G))


def test_euler_lb_K_5_is_one():
    """K_5: n=5, m=10, planar bound m - (3n - 6) = 10 - 9 = 1.
    Known cr(K_5) = 1, tight."""
    G = nx.complete_graph(5)
    assert crossing_number_lb_euler(G) == 1


def test_euler_lb_K_4_is_zero():
    """K_4 is planar — Euler bound saturates to 0."""
    G = nx.complete_graph(4)
    assert crossing_number_lb_euler(G) == 0
