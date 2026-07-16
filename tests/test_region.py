"""region.build_region tests."""

import pytest

from weld_core.config import WeldParams
from weld_core.region import build_region
from weld_core.schema import FaceRecord

PARAMS = WeldParams()


def _face(id_, part, normal, plane_origin, vertices):
    return FaceRecord(
        id=id_,
        part=part,
        body="Body1",
        surface_type="planar",
        area=1.0,
        normal=normal,
        plane_origin=plane_origin,
        centroid=plane_origin,
        vertices=vertices,
        manual_review=False,
    )


def test_build_region_mid_plane_and_overlap_size():
    a = _face(
        "A/face_1", "PartA", [0, 0, 1], [0, 0, 1.0],
        [[0, 0, 1], [100, 0, 1], [100, 50, 1], [0, 50, 1]],
    )
    b = _face(
        "B/face_1", "PartB", [0, 0, -1], [0, 0, 1.05],
        [[10, 5, 1.05], [110, 5, 1.05], [110, 55, 1.05], [10, 55, 1.05]],
    )
    region = build_region(a, b, PARAMS)
    assert region is not None
    assert region.plane_origin[2] == pytest.approx(1.025, abs=1e-9)
    assert region.gap_mm == pytest.approx(0.05, abs=1e-9)
    assert region.angle_deg == pytest.approx(0.0, abs=1e-6)

    width = region.bbox_max_2d[0] - region.bbox_min_2d[0]
    height = region.bbox_max_2d[1] - region.bbox_min_2d[1]
    assert sorted([round(width, 6), round(height, 6)]) == [45.0, 90.0]


def test_build_region_returns_none_when_overlap_too_narrow():
    a = _face(
        "A/face_1", "PartA", [0, 0, 1], [0, 0, 1.0],
        [[0, 0, 1], [100, 0, 1], [100, 50, 1], [0, 50, 1]],
    )
    # Overlap in y is only 2mm (48..50), well under the default 5mm min width.
    b = _face(
        "B/face_1", "PartB", [0, 0, -1], [0, 0, 1.05],
        [[10, 48, 1.05], [110, 48, 1.05], [110, 80, 1.05], [10, 80, 1.05]],
    )
    assert build_region(a, b, PARAMS) is None
