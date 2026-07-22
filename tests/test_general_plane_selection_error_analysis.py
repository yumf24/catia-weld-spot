from __future__ import annotations

import json

import pytest

from weld_core.general_plane_selection_error_analysis import ErrorAnalysisInputError, join_error_analysis, load_and_join_error_analysis


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
