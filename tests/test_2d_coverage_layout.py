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
    for x, y in points:
        polygon.Add(gp_Pnt(x, y, 0))
    polygon.Close()
    return BRepBuilderAPI_MakeFace(polygon.Wire()).Face()


def _region(shape):
    return ExactPlanarInterfaceRegion(
        id="a::b", face_a_id="a", face_b_id="b", plane_origin=(0, 0, 0), normal=(0, 0, 1),
        common_area_mm2=1, coverage_a=1, coverage_b=1, effective_width_mm=1, shape=shape,
    )


def test_layout_uses_2d_grid_and_all_points_are_in_exact_rectangle():
    candidates, audit = layout_exact_region(_region(_face([(0, 0), (40, 0), (40, 40), (0, 40)])), WeldParams())
    assert len(candidates) > 4  # not the legacy one-dimensional centre line
    assert audit.grid_pitch_mm == math.sqrt(2) * 10
    assert all(point_in_exact_region(_region(_face([(0, 0), (40, 0), (40, 40), (0, 40)])).shape, c.position) for c in candidates)


def test_layout_rejects_hole_and_concavity_aabb_points():
    outer = _face([(0, 0), (60, 0), (60, 60), (0, 60)])
    hole = _face([(20, 20), (40, 20), (40, 40), (20, 40)])
    cut = BRepAlgoAPI_Cut(outer, hole)
    cut.Build()
    region = _region(cut.Shape())

    candidates, audit = layout_exact_region(region, WeldParams())

    assert candidates
    assert audit.rejected_outside_exact_region > 0
    assert all(not (20 < candidate.position[0] < 40 and 20 < candidate.position[1] < 40) for candidate in candidates)
    assert all(point_in_exact_region(region.shape, candidate.position) for candidate in candidates)
