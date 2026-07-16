"""Geometry helper tests — runnable on Mac now (Phase 0/2 foundation)."""

import numpy as np
import pytest

from weld_core import geometry as g


def test_normal_angle_ignores_sign():
    assert g.normal_angle_deg([0, 0, 1], [0, 0, -1]) == pytest.approx(0.0, abs=1e-9)
    assert g.normal_angle_deg([0, 0, 1], [0, 0, 1]) == pytest.approx(0.0, abs=1e-9)
    assert g.normal_angle_deg([0, 0, 1], [1, 0, 0]) == pytest.approx(90.0, abs=1e-9)


def test_gap_between_planes():
    gap = g.gap_between_planes([0, 0, 1.0], [0, 0, 1], [0, 0, 1.05])
    assert gap == pytest.approx(0.05, abs=1e-9)


def test_project_and_aabb_overlap():
    verts_a = [[0, 0, 1], [100, 0, 1], [100, 50, 1], [0, 50, 1]]
    verts_b = [[10, 5, 1.05], [110, 5, 1.05], [110, 55, 1.05], [10, 55, 1.05]]
    origin, normal = [0, 0, 1.0], [0, 0, 1]
    pa = g.project_to_plane(verts_a, origin, normal)
    pb = g.project_to_plane(verts_b, origin, normal)
    min_a, max_a = g.aabb_2d(pa)
    min_b, max_b = g.aabb_2d(pb)
    overlap = g.aabb_overlap_2d(min_a, max_a, min_b, max_b)
    assert overlap is not None
    lo, hi = overlap
    # overlap rectangle should be 90 x 45 in the plane
    assert np.allclose(sorted((hi - lo).tolist()), [45.0, 90.0], atol=1e-6)


def test_no_overlap_returns_none():
    assert g.aabb_overlap_2d([0, 0], [1, 1], [5, 5], [6, 6]) is None
