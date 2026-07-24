from __future__ import annotations

import json

import pytest

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.gp import gp_Pnt

from weld_core.exact_planar_interface_regions import build_exact_planar_interface_region, write_exact_region
from weld_core.general_plane_selection import GeneralPlaneFace, exact_projected_pair_overlap


def _shape(points):
    polygon = BRepBuilderAPI_MakePolygon()
    for x, y, z in points:
        polygon.Add(gp_Pnt(x, y, z))
    polygon.Close()
    return BRepBuilderAPI_MakeFace(polygon.Wire()).Face()


def _face(face_id, part, points):
    return GeneralPlaneFace(
        id=face_id,
        part=part,
        normal=(0.0, 0.0, 1.0),
        plane_origin=points[0],
        centroid=(5.0, 5.0, points[0][2]),
        vertices=tuple(points),
        shape=_shape(points),
    )


def test_exact_region_preserves_true_common_area_not_aabb_and_writes_brep(tmp_path):
    # The triangle's AABB fully covers the square, but its exact overlap is
    # only half the square.  Region geometry must therefore be the OCCT face.
    face_a = _face("a", "PartA", [(0, 0, 0), (10, 0, 0), (0, 10, 0)])
    face_b = _face("b", "PartB", [(0, 0, 0.05), (10, 0, 0.05), (10, 10, 0.05), (0, 10, 0.05)])
    measurement = exact_projected_pair_overlap(face_a, face_b)

    region = build_exact_planar_interface_region(face_a, face_b, measurement)

    assert region.common_area_mm2 == pytest.approx(50.0)
    assert region.effective_width_mm == pytest.approx(10.0)
    path = tmp_path / "region.brep"
    write_exact_region(region, path)
    assert path.is_file() and path.stat().st_size > 0


def test_region_audit_uses_portable_geometry_refs_only(tmp_path):
    row = {
        "id": "a::b",
        "geometry_ref": "exact_interface_regions/0001.brep",
        "common_area_mm2": 50.0,
        "effective_width_mm": 10.0,
    }
    path = tmp_path / "interface_region_audit.json"
    path.write_text(json.dumps({"regions": [row]}), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["regions"][0]["geometry_ref"].endswith(".brep")
    assert "bbox" not in json.dumps(loaded)
