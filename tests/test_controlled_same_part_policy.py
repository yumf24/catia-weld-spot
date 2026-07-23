from __future__ import annotations

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from weld_core.controlled_same_part_policy import (
    classify_same_part_topology,
    diagnose_same_part_topology,
    render_same_part_topology_markdown,
)
from weld_core.general_plane_selection import ExactPairMeasurement
from test_general_plane_selection_geometry import _face


def _box_faces():
    explorer = TopExp_Explorer(BRepPrimAPI_MakeBox(10, 10, 10).Shape(), TopAbs_FACE)
    faces = []
    while explorer.More():
        faces.append(TopoDS.Face_s(explorer.Current()))
        explorer.Next()
    return faces


def _with_shape(face_id, shape):
    face = _face(face_id, "part")
    return face.__class__(**{**face.__dict__, "shape": shape})


def test_topology_classifier_is_pair_order_independent_and_uses_occt_boundaries():
    faces = _box_faces()
    classifications = set()
    for left in faces:
        for right in faces:
            if left == right:
                continue
            face_a, face_b = _with_shape("a", left), _with_shape("b", right)
            forward = classify_same_part_topology(face_a, face_b)
            assert forward == classify_same_part_topology(face_b, face_a)
            classifications.add(forward)
    assert "shared_edge" in classifications
    assert "disjoint_boundaries" in classifications


def test_topology_unknown_is_rejected_when_shape_boundary_is_missing():
    face_a = _face("a", "part")
    face_b = _face("b", "part")
    face_b = face_b.__class__(**{**face_b.__dict__, "shape": None})
    assert classify_same_part_topology(face_a, face_b) == "topology_unknown"


def test_topology_diagnosis_records_exact_geometry_and_evaluation_only_ceiling():
    faces = [_face("fn", "one"), _face("fp", "one", z=0.2), _face("other", "one", z=0.3)]
    exact = iter([
        ExactPairMeasurement(0.0, 0.2, 50.0, 0.5, 0.5, 100.0, 100.0),
        ExactPairMeasurement(0.0, 0.3, 0.0, 0.0, 0.0, 100.0, 100.0, "zero_area_intersection"),
        ExactPairMeasurement(0.0, 0.1, 50.0, 0.5, 0.5, 100.0, 100.0),
    ])
    report = diagnose_same_part_topology(
        faces,
        baseline_true_positives=30,
        offline_truth_face_ids=["fn"],
        baseline_predicted_face_ids=[],
        exact_overlap=lambda *_: next(exact),
        projected_aabb_overlap=lambda *_: (5.0, 5.0),
        topology_classifier=lambda a, b: "shared_edge" if {a.id, b.id} == {"fn", "fp"} else "disjoint_boundaries",
    )

    assert report["scope"] == "offline_same_part_topology_diagnosis"
    assert report["production_behavior_changed"] is False
    assert report["review_count"] == 3
    row = report["pairs"][0]
    assert row["same_part_relation"] == "same_part"
    assert row["topology_class"] == "shared_edge"
    assert row["exact_common_area_mm2"] == 50.0
    assert row["effective_width_mm"] == 5.0
    assert row["score"] == 25.0
    assert row["recovery_status"] == "recoverable"
    assert report["evaluation_only"]["face_composition_by_topology"]["shared_edge"] == {
        "true_positives": 0, "false_positives": 1, "false_negatives": 1,
    }
    assert report["evaluation_only"]["theoretical_upper_true_positives"] == 31
    assert "Truth is used only" in render_same_part_topology_markdown(report)
