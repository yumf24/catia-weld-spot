from __future__ import annotations

import pytest

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.gp import gp_Pnt

from weld_core.general_plane_selection import GeneralPlaneFace
from weld_core.general_plane_selection_evaluation import (
    GeneralSelectionEvaluationThresholds,
    build_offline_truth_mapping,
    evaluate_general_plane_selection,
    evaluation_markdown,
)


def _shape(x0: float, x1: float, y0: float = 0.0, y1: float = 10.0, z: float = 0.0):
    polygon = BRepBuilderAPI_MakePolygon()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        polygon.Add(gp_Pnt(x, y, z))
    polygon.Close()
    return BRepBuilderAPI_MakeFace(polygon.Wire()).Face()


def _face(
    face_id: str,
    *,
    part: str = "P",
    x0: float = 0.0,
    x1: float = 10.0,
    z: float = 0.0,
    normal: tuple[float, float, float] = (0.0, 0.0, 1.0),
) -> GeneralPlaneFace:
    return GeneralPlaneFace(
        id=face_id,
        part=part,
        normal=normal,
        plane_origin=(x0, 0.0, z),
        centroid=((x0 + x1) / 2.0, 5.0, z),
        vertices=((x0, 0.0, z), (x1, 0.0, z), (x1, 10.0, z), (x0, 10.0, z)),
        shape=_shape(x0, x1, z=z),
    )


def test_one_to_one_truth_mapping_uses_exact_overlap_evidence():
    result = build_offline_truth_mapping([_face("source")], [_face("reference")])

    assert result["summary"]["passed"] is True
    assert result["truth_face_ids"] == ["source"]
    candidate = result["reference_faces"][0]["candidates"][0]
    assert candidate["common_area_mm2"] == pytest.approx(100.0)
    assert candidate["source_coverage"] == pytest.approx(1.0)
    assert candidate["reference_coverage"] == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("source", "expected_reason"),
    [
        (_face("source", x0=10.0, x1=20.0), "no_unique_source_face_with_required_coverage"),
        (_face("source", x0=0.0, x1=9.0), "no_unique_source_face_with_required_coverage"),
    ],
)
def test_edge_contact_and_low_coverage_fail_truth_mapping(source, expected_reason):
    result = build_offline_truth_mapping([source], [_face("reference")])

    assert result["summary"]["passed"] is False
    assert result["reference_faces"][0]["reason"] == expected_reason


def test_ambiguous_reference_mapping_fails_instead_of_guessing():
    result = build_offline_truth_mapping([_face("source-a"), _face("source-b", x0=0.1, x1=10.1)], [_face("reference")])

    assert result["summary"]["passed"] is False
    assert result["reference_faces"][0]["status"] == "ambiguous"
    assert result["reference_faces"][0]["reason"] == "ambiguous_multiple_source_faces"


def test_angle_and_plane_distance_are_recorded_as_candidate_rejections():
    thresholds = GeneralSelectionEvaluationThresholds(plane_distance_mm_max=0.05)
    result = build_offline_truth_mapping(
        [_face("angled", normal=(0.0, 0.02, 1.0)), _face("distant", z=0.1)],
        [_face("reference")],
        thresholds,
    )

    reasons = {candidate["source_face_id"]: candidate["reason"] for candidate in result["reference_faces"][0]["candidates"]}
    assert reasons["angled"] == "normal_angle_exceeds_threshold"
    assert reasons["distant"] == "plane_distance_exceeds_threshold"


def test_prediction_metrics_report_tp_fp_fn_and_reasons():
    source_faces = [_face("truth"), _face("extra", x0=20.0, x1=30.0)]
    result = evaluate_general_plane_selection(source_faces, [_face("reference")], ["truth", "extra", "missing"])

    assert result["summary"]["true_positives"] == 1
    assert result["summary"]["false_positives"] == 2
    assert result["summary"]["false_negatives"] == 0
    assert result["summary"]["precision"] == pytest.approx(1 / 3)
    assert {row["reason"] for row in result["false_positive_faces"]} == {
        "predicted_face_not_in_offline_truth",
        "unknown_predicted_face",
    }


def test_failed_truth_mapping_prevents_silent_metric_success():
    result = evaluate_general_plane_selection([_face("source-a"), _face("source-b", x0=0.1, x1=10.1)], [_face("reference")], ["source-a"])

    assert result["summary"]["passed"] is False
    assert result["summary"]["truth_faces"] == 0
    assert result["summary"]["false_positives"] == 1


def test_markdown_summary_is_human_readable():
    result = evaluate_general_plane_selection([_face("truth")], [_face("reference")], ["truth"])

    markdown = evaluation_markdown(result)

    assert "TP / FP / FN: 1 / 0 / 0" in markdown
    assert "Precision: 100.00%" in markdown
