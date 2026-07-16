"""points.layout_points tests."""

import numpy as np
import pytest

from weld_core.config import WeldParams
from weld_core.points import layout_points
from weld_core.region import Region

PARAMS = WeldParams()


def _region(bbox_min_2d, bbox_max_2d):
    return Region(
        face_a_id="A/face_1",
        face_b_id="B/face_1",
        plane_origin=(0.0, 0.0, 1.025),
        normal=(0.0, 0.0, 1.0),
        bbox_min_2d=bbox_min_2d,
        bbox_max_2d=bbox_max_2d,
        gap_mm=0.05,
        angle_deg=0.0,
    )


def _within_bbox(candidate):
    lo, hi = np.asarray(candidate.region_bbox.min), np.asarray(candidate.region_bbox.max)
    pos = np.asarray(candidate.position)
    assert np.all(pos >= lo - 1e-6) and np.all(pos <= hi + 1e-6)


def test_small_region_gets_single_center_point():
    region = _region((0.0, 0.0), (10.0, 8.0))  # long_dim=10 < default min_spacing_mm=20
    candidates = layout_points(region, PARAMS)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.spacing_mm == pytest.approx(0.0)
    assert c.position[2] == pytest.approx(1.025)
    assert c.layer_type == "two_layer"
    assert c.faces == ["A/face_1", "B/face_1"]
    _within_bbox(c)


def test_long_region_gets_evenly_spaced_points():
    region = _region((0.0, 0.0), (90.0, 45.0))  # long_dim=90
    candidates = layout_points(region, PARAMS)
    assert len(candidates) == 3
    for c in candidates:
        assert c.spacing_mm == pytest.approx(45.0)
        assert c.position[2] == pytest.approx(1.025)
        _within_bbox(c)

    # Positions should be evenly spaced ~45mm apart along whichever axis
    # varies (the long one) -- check via pairwise 3D distance since the
    # exact in-plane basis convention isn't part of the public contract.
    positions = np.array([c.position for c in candidates])
    dists = np.linalg.norm(np.diff(positions, axis=0), axis=1)
    assert np.allclose(sorted(dists), [45.0, 45.0], atol=1e-6)


def test_spacing_never_exceeds_max_spacing_mm():
    region = _region((0.0, 0.0), (1000.0, 30.0))
    candidates = layout_points(region, PARAMS)
    assert len(candidates) >= 2
    assert candidates[0].spacing_mm <= PARAMS.max_spacing_mm + 1e-9
    assert candidates[0].spacing_mm >= PARAMS.min_spacing_mm - 1e-9
