from __future__ import annotations

import pytest

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.gp import gp_Pnt

from weld_core.general_plane_selection import (
    GeneralPlaneFace,
    GeneralSelectionParams,
    evaluate_pair,
    exact_projected_pair_overlap,
    select_general_planar_faces,
)


def _rectangle_shape(x0: float, x1: float, y0: float = 0.0, y1: float = 10.0, z: float = 0.0):
    polygon = BRepBuilderAPI_MakePolygon()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        polygon.Add(gp_Pnt(x, y, z))
    polygon.Close()
    return BRepBuilderAPI_MakeFace(polygon.Wire()).Face()


def _face(
    face_id: str,
    part: str,
    *,
    x0: float = 0.0,
    x1: float = 10.0,
    y0: float = 0.0,
    y1: float = 10.0,
    z: float = 0.0,
    normal: tuple[float, float, float] = (0.0, 0.0, 1.0),
) -> GeneralPlaneFace:
    return GeneralPlaneFace(
        id=face_id,
        part=part,
        normal=normal,
        plane_origin=(x0, y0, z),
        centroid=((x0 + x1) / 2.0, (y0 + y1) / 2.0, z),
        vertices=((x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)),
        shape=_rectangle_shape(x0, x1, y0, y1, z),
    )


def test_exact_projected_overlap_measures_parallel_faces_with_gap():
    face_a = _face("a", "PartA")
    face_b = _face("b", "PartB", x0=2.0, x1=12.0, z=0.05, normal=(0.0, 0.0, -1.0))

    overlap = exact_projected_pair_overlap(face_a, face_b)

    assert overlap.matched
    assert overlap.plane_gap_mm == pytest.approx(0.05)
    assert overlap.normal_angle_deg == pytest.approx(0.0)
    assert overlap.common_area_mm2 == pytest.approx(80.0)
    assert overlap.coverage_a == pytest.approx(0.8)
    assert overlap.coverage_b == pytest.approx(0.8)


def test_pair_acceptance_records_exact_metrics_and_score():
    audit = evaluate_pair(
        _face("a", "PartA"),
        _face("b", "PartB", x0=5.0, x1=15.0, z=0.05),
        GeneralSelectionParams(min_overlap_area_mm2=1.0, min_face_coverage=0.1),
    )

    assert audit.accepted
    assert audit.reason is None
    assert audit.common_area_mm2 == pytest.approx(50.0)
    assert audit.coverage_a == pytest.approx(0.5)
    assert audit.coverage_b == pytest.approx(0.5)
    assert audit.score == pytest.approx(25.0)


def test_projected_aabb_only_prescreens_and_edge_contact_is_rejected_by_exact_overlap():
    audit = evaluate_pair(
        _face("a", "PartA"),
        _face("b", "PartB", x0=10.0, x1=20.0, z=0.05),
        GeneralSelectionParams(min_effective_width_mm=0.0),
    )

    assert not audit.accepted
    assert audit.reason == "projected_aabb_no_overlap"
    assert audit.common_area_mm2 == 0.0


def test_spatially_separate_faces_are_rejected_before_exact_boolean_work():
    audit = evaluate_pair(_face("a", "PartA"), _face("b", "PartB", x0=20.0, x1=30.0, z=0.05))

    assert not audit.accepted
    assert audit.reason == "projected_aabb_no_overlap"


def test_same_part_pairs_are_explicitly_excluded_by_default():
    audit = evaluate_pair(_face("a", "PartA"), _face("b", "PartA", z=0.05))

    assert not audit.accepted
    assert audit.reason == "same_part_excluded"


@pytest.mark.parametrize(
    ("face_b", "params", "reason"),
    [
        (
            _face("b", "PartB", z=0.5),
            GeneralSelectionParams(max_plane_gap_mm=0.2),
            "plane_gap_exceeds_threshold",
        ),
        (
            _face("b", "PartB", normal=(0.0, 0.2, 0.98)),
            GeneralSelectionParams(max_normal_angle_deg=0.5),
            "normal_angle_exceeds_threshold",
        ),
        (
            _face("b", "PartB", x0=9.95, x1=19.95),
            GeneralSelectionParams(min_effective_width_mm=0.1),
            "effective_width_below_threshold",
        ),
        (
            _face("b", "PartB", x0=9.0, x1=19.0),
            GeneralSelectionParams(min_face_coverage=0.2),
            "coverage_below_threshold",
        ),
    ],
)
def test_rejection_reasons_are_auditable(face_b, params, reason):
    audit = evaluate_pair(_face("a", "PartA"), face_b, params)

    assert not audit.accepted
    assert audit.reason == reason


def test_selected_faces_are_deduplicated_with_supporting_pair_traceability():
    face_a = _face("a", "PartA")
    face_b = _face("b", "PartB", z=0.05)
    face_c = _face("c", "PartC", x0=1.0, x1=11.0, z=0.1)

    result = select_general_planar_faces([face_c, face_a, face_b])

    assert result.selected_face_ids == ("a", "b", "c")
    assert len(result.supporting_pair_ids_by_face["a"]) == 2
    assert sum(audit.common_area_mm2 for audit in result.pair_audits if audit.face_a_id == "a") == pytest.approx(190.0)
    assert all(audit.accepted for audit in result.pair_audits)
