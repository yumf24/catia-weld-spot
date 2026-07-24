from __future__ import annotations

from weld_core.general_plane_selection import GeneralPlaneFace
from weld_core.planar_truth_adjudication import (
    InterfaceEvidence,
    PlanarTruthParams,
    adjudicate_planar_truth,
    adjudication_markdown,
)
from weld_core.schema import GroundTruthPoint


def _face(face_id: str, part: str, *, z: float = 0.0, normal=(0.0, 0.0, 1.0)) -> GeneralPlaneFace:
    return GeneralPlaneFace(
        id=face_id,
        part=part,
        normal=normal,
        plane_origin=(0.0, 0.0, z),
        centroid=(0.0, 0.0, z),
        vertices=((0.0, 0.0, z), (10.0, 0.0, z), (0.0, 10.0, z)),
        area_mm2=50.0,
        shape=None,
    )


def _point(point_id="gt-1"):
    return GroundTruthPoint(id=point_id, position=(2.0, 2.0, 0.1))


def _evidence(face_a, face_b, _point, _params, *, relation="inside_exact_common_region", reason=None):
    return InterfaceEvidence(face_a.id, face_b.id, face_a.part, face_b.part, 0.0, 0.2, 25.0, relation, reason)


def test_marks_one_exact_different_part_interface_as_planar_supported():
    report = adjudicate_planar_truth([_point()], [_face("a", "one"), _face("b", "two", z=0.2)], interface_builder=_evidence)

    row = report["points"][0]
    assert row["status"] == "planar_supported"
    assert row["reason"] is None
    assert row["layer_count"] == 2
    assert row["supporting_interfaces"][0]["common_area_mm2"] == 25.0
    assert "evaluation-only" in adjudication_markdown(report)


def test_no_qualifying_planar_interface_is_retained_as_unresolved():
    report = adjudicate_planar_truth([_point()], [_face("a", "one"), _face("b", "one", z=0.2)], interface_builder=_evidence)

    row = report["points"][0]
    assert row["status"] == "out_of_scope_or_unresolved"
    assert row["reason"] == "no_qualifying_planar_interface"
    assert row["evaluated_interfaces"] == []


def test_point_outside_exact_common_region_is_not_supported():
    report = adjudicate_planar_truth(
        [_point()],
        [_face("a", "one"), _face("b", "two", z=0.2)],
        interface_builder=lambda *args: _evidence(*args, relation="outside_exact_common_region"),
    )

    assert report["points"][0]["reason"] == "outside_exact_common_region"


def test_multiple_feasible_interfaces_are_explicitly_ambiguous():
    report = adjudicate_planar_truth(
        [_point()],
        [_face("a", "one"), _face("b", "two", z=0.2), _face("c", "three", z=0.1)],
        interface_builder=_evidence,
    )

    row = report["points"][0]
    assert row["status"] == "out_of_scope_or_unresolved"
    assert row["reason"] == "ambiguous_multiple_feasible_interfaces"
    assert len(row["supporting_interfaces"]) == 3


def test_occt_exception_is_retained_as_insufficient_evidence():
    report = adjudicate_planar_truth(
        [_point()],
        [_face("a", "one"), _face("b", "two", z=0.2)],
        interface_builder=lambda *args: _evidence(*args, relation="unresolved", reason="occt_exception:RuntimeError"),
    )

    row = report["points"][0]
    assert row["status"] == "out_of_scope_or_unresolved"
    assert row["reason"] == "insufficient_exact_geometry_evidence"


def test_angle_and_gap_limits_prevent_builder_calls():
    calls = []
    report = adjudicate_planar_truth(
        [_point()],
        [_face("a", "one"), _face("b", "two", z=2.0), _face("c", "three", normal=(1.0, 0.0, 0.0))],
        params=PlanarTruthParams(max_plane_gap_mm=1.5),
        interface_builder=lambda *args: calls.append(args) or _evidence(*args),
    )

    assert calls == []
    assert report["points"][0]["reason"] == "no_qualifying_planar_interface"
