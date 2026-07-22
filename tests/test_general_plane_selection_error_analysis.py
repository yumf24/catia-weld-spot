from __future__ import annotations

import json

import pytest

from weld_core.general_plane_selection_error_analysis import (
    ErrorAnalysisInputError,
    classify_false_negatives,
    classify_false_positives,
    join_error_analysis,
    load_and_join_error_analysis,
)


def _artifacts():
    evaluation = {
        "summary": {"true_positives": 1, "false_positives": 1, "false_negatives": 1},
        "true_positive_faces": [{"face_id": "truth-selected"}],
        "false_positive_faces": [{"face_id": "extra-selected"}],
        "false_negative_faces": [{"face_id": "truth-rejected"}],
    }
    pair_audit = {
        "pairs": [
            {"id": "accepted", "face_a_id": "truth-selected", "face_b_id": "extra-selected", "accepted": True},
            {"id": "rejected", "face_a_id": "truth-rejected", "face_b_id": "other-rejected", "accepted": False},
        ]
    }
    selection_audit = {
        "parameters": {"max_plane_gap_mm": 0.2},
        "total_planar_faces": 4,
        "selected_face_count": 2,
        "selected_faces": [
            {"face_id": "truth-selected", "supporting_pair_ids": ["accepted"]},
            {"face_id": "extra-selected", "supporting_pair_ids": ["accepted"]},
        ],
        "rejected_faces": [
            {"face_id": "truth-rejected", "reason": "no_accepted_pair"},
            {"face_id": "other-rejected", "reason": "no_accepted_pair"},
        ],
    }
    return evaluation, pair_audit, selection_audit


def test_join_combines_tp_fp_fn_with_selected_source_and_supporting_pairs():
    result = join_error_analysis(*_artifacts())

    by_face = {row["face_id"]: row for row in result["faces"]}
    assert by_face["truth-selected"]["classification"] == "true_positive"
    assert by_face["extra-selected"]["classification"] == "false_positive"
    assert by_face["truth-rejected"]["classification"] == "false_negative"
    assert by_face["truth-rejected"]["selection_status"] == "rejected"
    assert by_face["truth-selected"]["supporting_pairs"] == [_artifacts()[1]["pairs"][0]]


def test_join_rejects_unknown_prediction_not_present_in_selection_audit():
    evaluation, pair_audit, selection_audit = _artifacts()
    evaluation["false_positive_faces"].append({"face_id": "unknown"})
    evaluation["summary"]["false_positives"] = 2

    with pytest.raises(ErrorAnalysisInputError, match="predictions and selection audit differ"):
        join_error_analysis(evaluation, pair_audit, selection_audit)


def test_join_rejects_missing_supporting_pair_audit():
    evaluation, pair_audit, selection_audit = _artifacts()
    selection_audit["selected_faces"][0]["supporting_pair_ids"] = ["missing"]

    with pytest.raises(ErrorAnalysisInputError, match="references missing pair"):
        join_error_analysis(evaluation, pair_audit, selection_audit)


def test_load_and_join_reads_explicit_artifact_paths(tmp_path):
    paths = []
    for name, value in zip(("evaluation.json", "pairs.json", "selection.json"), _artifacts(), strict=True):
        path = tmp_path / name
        path.write_text(json.dumps(value), encoding="utf-8")
        paths.append(path)

    result = load_and_join_error_analysis(*paths)

    assert result["summary"]["true_positives"] == 1


def test_fn_classification_prefers_gap_evidence_and_preserves_geometry_fields():
    evaluation, pair_audit, selection_audit = _artifacts()
    pair_audit["pairs"][1].update(
        {
            "reason": "plane_gap_exceeds_threshold",
            "part_a": "primary",
            "part_b": "reference",
            "normal_angle_deg": 0.1,
            "plane_gap_mm": 0.8,
            "aabb_overlap_width_mm": None,
            "aabb_overlap_height_mm": None,
            "common_area_mm2": 0.0,
            "coverage_a": 0.0,
            "coverage_b": 0.0,
        }
    )

    result = classify_false_negatives(join_error_analysis(evaluation, pair_audit, selection_audit), pair_audit)

    assert result == [
        {
            "face_id": "truth-rejected",
            "failure_stage": "plane_gap",
            "recommended_recovery": "investigate_gap_threshold_or_layered_gap_strategy",
            "best_failed_pair": {
                "pair_id": "rejected",
                "reason": "plane_gap_exceeds_threshold",
                "counterpart_face_id": "other-rejected",
                "parts": {"source_part": "primary", "counterpart_part": "reference", "relation": "different_parts"},
                "normal_angle_deg": 0.1,
                "plane_gap_mm": 0.8,
                "aabb_overlap_width_mm": None,
                "aabb_overlap_height_mm": None,
                "common_area_mm2": 0.0,
                "coverage_a": 0.0,
                "coverage_b": 0.0,
            },
        }
    ]


def test_fn_classification_prefers_projected_aabb_to_gap_and_same_part():
    evaluation, pair_audit, selection_audit = _artifacts()
    selection_audit["rejected_faces"].extend(
        [
            {"face_id": "same-part-face", "reason": "no_accepted_pair"},
            {"face_id": "aabb-face", "reason": "no_accepted_pair"},
        ]
    )
    selection_audit["total_planar_faces"] = 6
    pair_audit["pairs"].extend(
        [
            {
                "id": "same-part",
                "face_a_id": "truth-rejected",
                "face_b_id": "same-part-face",
                "part_a": "one",
                "part_b": "one",
                "accepted": False,
                "reason": "same_part_excluded",
            },
            {
                "id": "aabb",
                "face_a_id": "truth-rejected",
                "face_b_id": "aabb-face",
                "part_a": "one",
                "part_b": "two",
                "accepted": False,
                "reason": "projected_aabb_no_overlap",
                "plane_gap_mm": 0.1,
                "common_area_mm2": 0.0,
                "coverage_a": 0.0,
                "coverage_b": 0.0,
            },
        ]
    )

    result = classify_false_negatives(join_error_analysis(evaluation, pair_audit, selection_audit), pair_audit)

    assert result[0]["failure_stage"] == "projected_aabb"
    assert result[0]["recommended_recovery"] == "diagnose_projected_aabb_pre_filter"
    assert result[0]["best_failed_pair"]["pair_id"] == "aabb"


def test_fn_classification_uses_same_part_when_no_deeper_geometry_evidence_exists():
    evaluation, pair_audit, selection_audit = _artifacts()
    selection_audit["rejected_faces"].append({"face_id": "same-part-face", "reason": "no_accepted_pair"})
    selection_audit["total_planar_faces"] = 5
    pair_audit["pairs"][1].update({"reason": "same_part_excluded", "part_a": "one", "part_b": "one"})

    result = classify_false_negatives(join_error_analysis(evaluation, pair_audit, selection_audit), pair_audit)

    assert result[0]["failure_stage"] == "same_part_policy"
    assert result[0]["recommended_recovery"] == "evaluate_same_part_pair_policy"


def test_fp_classification_explains_single_support_connected_to_truth():
    evaluation, pair_audit, selection_audit = _artifacts()
    pair_audit["pairs"][0].update(
        {"part_a": "truth-part", "part_b": "extra-part", "common_area_mm2": 12.0, "coverage_a": 0.8, "coverage_b": 0.7, "score": 6.72}
    )

    result = classify_false_positives(join_error_analysis(evaluation, pair_audit, selection_audit))

    assert result == [
        {
            "face_id": "extra-selected",
            "is_unknown_predicted_face": True,
            "false_positive_reason": "accepted_pair_connects_offline_truth",
            "supporting_pairs": [
                {
                    "pair_id": "accepted",
                    "counterpart_face_id": "truth-selected",
                    "counterpart_part": "truth-part",
                    "counterpart_is_truth_face": True,
                    "common_area_mm2": 12.0,
                    "coverage_a": 0.8,
                    "coverage_b": 0.7,
                    "score": 6.72,
                }
            ],
        }
    ]


def test_fp_classification_retains_multiple_supports_and_identifies_non_truth_pairs():
    evaluation, pair_audit, selection_audit = _artifacts()
    pair_audit["pairs"].append(
        {
            "id": "accepted-extra",
            "face_a_id": "extra-selected",
            "face_b_id": "other-selected",
            "part_a": "extra-part",
            "part_b": "other-part",
            "accepted": True,
            "common_area_mm2": 3.0,
            "coverage_a": 0.2,
            "coverage_b": 0.3,
            "score": 0.18,
        }
    )
    selection_audit["selected_faces"][1]["supporting_pair_ids"].append("accepted-extra")
    selection_audit["selected_faces"].append({"face_id": "other-selected", "supporting_pair_ids": ["accepted-extra"]})
    selection_audit["selected_face_count"] = 3
    selection_audit["total_planar_faces"] = 6
    selection_audit["rejected_faces"].append({"face_id": "other-rejected-2", "reason": "no_accepted_pair"})
    evaluation["false_positive_faces"].append({"face_id": "other-selected"})
    evaluation["summary"]["false_positives"] = 2

    result = classify_false_positives(join_error_analysis(evaluation, pair_audit, selection_audit))

    extra = next(row for row in result if row["face_id"] == "extra-selected")
    assert len(extra["supporting_pairs"]) == 2
    assert extra["supporting_pairs"][1]["counterpart_is_truth_face"] is False
    other = next(row for row in result if row["face_id"] == "other-selected")
    assert other["false_positive_reason"] == "accepted_pair_not_in_offline_truth"
