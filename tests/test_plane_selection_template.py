from __future__ import annotations

from copy import deepcopy

import pytest
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.gp import gp_Pnt

from weld_core.plane_reference_labels import IndexedStepFace, build_reference_face_labels
from weld_core.plane_selection_template import TemplateValidationError, build_template, validate_template
from weld_core.step_geometry import StepFace


def _indexed(index: int) -> IndexedStepFace:
    polygon = BRepBuilderAPI_MakePolygon()
    for x, y in ((0, 0), (10, 0), (10, 10), (0, 10)):
        polygon.Add(gp_Pnt(x, y, 0))
    polygon.Close()
    face = BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
    return IndexedStepFace("P", index, StepFace("P", [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)], (5, 5, 0), (0, 0, 1), 100, True, 0, face))


def _template():
    source = _indexed(3)
    result = build_reference_face_labels([source], [_indexed(7)])
    result["part_id"] = "component-simplify"
    return build_template(result, [source], [
        {"role": "primary_model", "sha256": "a" * 64},
        {"role": "surface_reference", "sha256": "b" * 64},
    ])


def test_valid_template_round_trips_with_single_cad_face_identity():
    template = _template()
    validate_template(template)
    assert template["selected_faces"][0]["step_face_index"] == 3


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "bad_hash", "bad_fingerprint", "low_coverage"])
def test_invalid_template_contracts_are_rejected(mutation):
    template = deepcopy(_template())
    if mutation == "missing":
        del template["selected_faces"][0]["normal"]
    elif mutation == "duplicate":
        template["selected_faces"].append(deepcopy(template["selected_faces"][0]))
    elif mutation == "bad_hash":
        template["source_sha256"] = "bad"
    elif mutation == "bad_fingerprint":
        template["selected_faces"][0]["boundary_fingerprint"]["vertices_sha256"] = "bad"
    else:
        template["selected_faces"][0]["source_coverage"] = 0.94
    with pytest.raises(TemplateValidationError):
        validate_template(template)
