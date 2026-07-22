from __future__ import annotations

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.gp import gp_Pnt

from weld_core.plane_reference_labels import IndexedStepFace, build_reference_face_labels
from weld_core.step_geometry import StepFace


def _rect(x0, x1):
    polygon = BRepBuilderAPI_MakePolygon()
    for x, y in ((x0, 0), (x1, 0), (x1, 10), (x0, 10)):
        polygon.Add(gp_Pnt(x, y, 0))
    polygon.Close()
    shape = BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
    return StepFace("P", centroid=((x0 + x1) / 2, 5, 0), normal=(0, 0, 1), area=(x1 - x0) * 10, is_planar=True, shape=shape)


def _indexed(index, x0, x1):
    return IndexedStepFace("P", index, _rect(x0, x1))


def test_one_to_one_label_is_selected_with_exact_audit():
    result = build_reference_face_labels([_indexed(0, 0, 10)], [_indexed(5, 0, 10)])
    assert result["summary"]["passed"] is True
    assert result["labels"][0]["source_face_id"] == "P/step_face_0000"
    assert result["labels"][0]["source_coverage"] == 1.0


def test_edge_contact_does_not_create_a_label():
    result = build_reference_face_labels([_indexed(0, 0, 10)], [_indexed(5, 10, 20)])
    assert result["summary"]["passed"] is False
    assert result["reference_audit"][0]["rejection_reason"] == "no_single_face_with_required_source_coverage"


def test_one_reference_to_multiple_source_faces_is_rejected_as_ambiguous():
    result = build_reference_face_labels([_indexed(0, 0, 10), _indexed(1, 0.1, 10)], [_indexed(5, 0, 10)])
    assert result["summary"]["passed"] is False
    assert result["reference_audit"][0]["rejection_reason"] == "ambiguous_multiple_source_faces"


def test_split_source_cannot_be_guessed_as_a_single_face_label():
    result = build_reference_face_labels([_indexed(0, 0, 5), _indexed(1, 5, 10)], [_indexed(5, 0, 10)])
    assert result["summary"]["passed"] is False
    assert result["reference_audit"][0]["rejection_reason"] == "ambiguous_multiple_source_faces"
