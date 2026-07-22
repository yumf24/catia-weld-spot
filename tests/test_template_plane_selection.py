from __future__ import annotations

from copy import deepcopy

import pytest
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.gp import gp_Pnt

from weld_core.plane_reference_labels import IndexedStepFace, build_reference_face_labels
from weld_core.plane_selection_template import build_template
from weld_core.step_geometry import StepFace
from weld_core.template_plane_selection import TemplateSelectionError, select_template_planes, validate_primary_sha


def _face(index: int, x_offset: float = 0.0) -> IndexedStepFace:
    polygon = BRepBuilderAPI_MakePolygon()
    for x, y in ((0, 0), (10, 0), (10, 10), (0, 10)):
        polygon.Add(gp_Pnt(x + x_offset, y, 0))
    polygon.Close()
    shape = BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
    return IndexedStepFace(
        "P", index,
        StepFace("P", [(x_offset, 0, 0), (x_offset + 10, 0, 0), (x_offset + 10, 10, 0), (x_offset, 10, 0)],
                 (x_offset + 5, 5, 0), (0, 0, 1), 100, True, 0, shape),
    )


def _template() -> dict:
    selected = _face(3)
    labels = build_reference_face_labels([selected], [_face(7)])
    labels["part_id"] = "component-simplify"
    return build_template(labels, [selected], [
        {"role": "primary_model", "sha256": "a" * 64},
        {"role": "surface_reference", "sha256": "b" * 64},
    ])


def test_template_selection_is_stable_and_audits_every_primary_plane():
    template = _template()
    # Index 0 is non-planar and intentionally must not be selected/audited as a plane.
    non_planar = _face(0)
    non_planar.face.is_planar = False
    selected, audit = select_template_planes(template, {"P": [non_planar.face, _face(1, 20).face, _face(2, 40).face, _face(3).face]})
    selected_again, audit_again = select_template_planes(template, {"P": [non_planar.face, _face(1, 20).face, _face(2, 40).face, _face(3).face]})
    assert [face.id for face in selected.faces] == ["P/step_face_0003"]
    assert [face.id for face in selected_again.faces] == [face.id for face in selected.faces]
    assert audit["summary"] == {"primary_planar_faces": 3, "selected_faces": 1, "excluded_faces": 2, "passed": True}
    assert audit_again == audit
    assert {row["reason"] for row in audit["faces"]} == {
        "template_identity_and_fingerprint_verified", "not_in_frozen_template"
    }


@pytest.mark.parametrize("mutation", ["missing_index", "fingerprint"])
def test_template_selection_rejects_identity_or_fingerprint_mismatch(mutation):
    template = deepcopy(_template())
    source = _face(3)
    if mutation == "missing_index":
        source = _face(4)
        groups = {"P": [source.face]}
    else:
        changed = _face(3, 1)
        groups = {"P": [_face(0, -30).face, _face(1, -20).face, _face(2, -10).face, changed.face]}
    with pytest.raises(TemplateSelectionError):
        select_template_planes(template, groups)


def test_template_selection_rejects_a_different_primary_sha_before_parsing_or_writing():
    with pytest.raises(TemplateSelectionError, match="SHA-256 differs"):
        validate_primary_sha(_template(), "c" * 64)
