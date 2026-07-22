from __future__ import annotations

import pytest

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.gp import gp_Pnt

from weld_core.exact_face_overlap import CoplanarFacePair, exact_face_overlap, source_union_coverage


def _rectangle(x0: float, x1: float, y0: float = 0.0, y1: float = 10.0, z: float = 0.0):
    polygon = BRepBuilderAPI_MakePolygon()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        polygon.Add(gp_Pnt(x, y, z))
    polygon.Close()
    return BRepBuilderAPI_MakeFace(polygon.Wire()).Face()


def _pair(source, reference, *, angle: float = 0.0, distance: float = 0.0):
    return CoplanarFacePair(source, reference, angle, distance)


def test_exact_overlap_reports_full_bidirectional_coverage():
    overlap = exact_face_overlap(_pair(_rectangle(0, 10), _rectangle(0, 10)))
    assert overlap.matched
    assert overlap.common_area_mm2 == pytest.approx(100.0)
    assert overlap.source_coverage == pytest.approx(1.0)
    assert overlap.reference_coverage == pytest.approx(1.0)


def test_exact_overlap_reports_ninety_five_percent_source_coverage():
    overlap = exact_face_overlap(_pair(_rectangle(0, 10), _rectangle(0, 9.5)))
    assert overlap.source_coverage == pytest.approx(0.95)


@pytest.mark.parametrize("reference", [_rectangle(10, 20), _rectangle(10, 20, 10, 20)])
def test_boundary_or_point_contact_has_no_match(reference):
    overlap = exact_face_overlap(_pair(_rectangle(0, 10), reference))
    assert not overlap.matched
    assert overlap.common_area_mm2 == 0.0
    assert overlap.reason == "zero_area_intersection"


def test_partial_overlap_uses_true_cad_boundary_not_aabb_heuristic():
    overlap = exact_face_overlap(_pair(_rectangle(0, 10), _rectangle(5, 15)))
    assert overlap.common_area_mm2 == pytest.approx(50.0)
    assert overlap.source_coverage == pytest.approx(0.5)


def test_non_coplanar_faces_cannot_match_even_with_identical_xy_boundaries():
    overlap = exact_face_overlap(_pair(_rectangle(0, 10), _rectangle(0, 10, z=1.0), distance=1.0))
    assert not overlap.matched
    assert overlap.reason == "plane_distance_exceeds_tolerance"


@pytest.mark.parametrize(
    ("angle", "distance", "expected_reason"),
    [(0.51, 0.0, "normal_angle_exceeds_tolerance"), (0.0, 0.051, "plane_distance_exceeds_tolerance")],
)
def test_over_tolerance_coplanar_qualification_cannot_match(angle, distance, expected_reason):
    overlap = exact_face_overlap(_pair(_rectangle(0, 10), _rectangle(0, 10), angle=angle, distance=distance))
    assert not overlap.matched
    assert overlap.reason == expected_reason


def test_multiple_reference_faces_are_fused_before_source_coverage_is_measured():
    source = _rectangle(0, 10)
    coverage = source_union_coverage([
        _pair(source, _rectangle(0, 7)),
        _pair(source, _rectangle(5, 10)),
    ])
    assert coverage.common_area_mm2 == pytest.approx(100.0)
    assert coverage.source_coverage == pytest.approx(1.0)
