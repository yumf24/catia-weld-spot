from __future__ import annotations

import math

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.gp import gp_Pnt

from weld_core.config import WeldParams
from weld_core.coverage_layout import layout_exact_region, point_in_exact_region
from weld_core.exact_planar_interface_regions import ExactPlanarInterfaceRegion


def _face(points):
    polygon = BRepBuilderAPI_MakePolygon()
    for point in points:
        polygon.Add(gp_Pnt(*point))
    polygon.Close()
    return BRepBuilderAPI_MakeFace(polygon.Wire()).Face()


def _region(shape, *, origin=(0, 0, 0), normal=(0, 0, 1)):
    return ExactPlanarInterfaceRegion(
        id="a::b", face_a_id="a", face_b_id="b", plane_origin=origin, normal=normal,
        common_area_mm2=1, coverage_a=1, coverage_b=1, effective_width_mm=1, shape=shape,
    )


def test_certificate_covers_rotated_offset_region_and_records_boundary_evidence():
    # The support plane is z=x+7, deliberately neither axis-aligned nor at 0.
    normal = (-1 / math.sqrt(2), 0, 1 / math.sqrt(2))
    points = [(0, 0, 7), (50, 0, 57), (50, 30, 57), (0, 30, 7)]
    region = _region(_face(points), origin=(0, 0, 7), normal=normal)

    candidates, audit = layout_exact_region(region, WeldParams())

    assert audit.layout_status == "certified"
    assert audit.layout_method == "exact_uv_adaptive_farthest_point_v1"
    assert audit.max_certificate_distance_mm <= 10 + 1e-9
    assert audit.max_projection_error_mm <= 1e-6
    assert audit.boundary_vertex_count >= 4
    assert all(point_in_exact_region(region.shape, point.position) for point in candidates)


def test_certificate_handles_hole_and_narrow_strip_without_zero_layout():
    outer = _face([(0, 0, 0), (60, 0, 0), (60, 60, 0), (0, 60, 0)])
    hole = _face([(20, 20, 0), (40, 20, 0), (40, 40, 0), (20, 40, 0)])
    cut = BRepAlgoAPI_Cut(outer, hole)
    cut.Build()
    candidates, audit = layout_exact_region(_region(cut.Shape()), WeldParams())
    assert candidates
    assert audit.max_certificate_distance_mm <= 10 + 1e-9
    assert all(not (20 < item.position[0] < 40 and 20 < item.position[1] < 40) for item in candidates)

    strip = _region(_face([(0, 0, 0), (80, 0, 0), (80, 2, 0), (0, 2, 0)]))
    candidates, audit = layout_exact_region(strip, WeldParams())
    assert candidates
    assert audit.max_certificate_distance_mm <= 10 + 1e-9
