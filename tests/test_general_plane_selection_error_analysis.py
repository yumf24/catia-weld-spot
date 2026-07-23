from __future__ import annotations

import json

import pytest

from weld_core.general_plane_selection_error_analysis import (
    ErrorAnalysisInputError,
    build_error_analysis_report,
    build_expanded_gap_false_positive_attribution,
    build_controlled_parameter_sweep,
    build_optimization_recommendation_backlog,
    classify_false_negatives,
    classify_false_positives,
    join_error_analysis,
    load_and_join_error_analysis,
    render_error_analysis_markdown,
    render_expanded_gap_false_positive_attribution_markdown,
    build_same_part_risk_report,
    render_same_part_risk_markdown,
    render_controlled_parameter_sweep_markdown,
)
from weld_core.general_plane_selection import ExactPairMeasurement
from weld_core.general_plane_selection_aabb_diagnosis import diagnose_projected_aabb_rejections
from test_general_plane_selection_geometry import _face


def test_aabb_diagnosis_classifies_exact_outcomes_and_is_stably_sorted():
    audit = {"pairs": [
        {"id": "z", "face_a_id": "a", "face_b_id": "b", "part_a": "one", "part_b": "two", "plane_gap_mm": 0.1, "reason": "projected_aabb_no_overlap"},
        {"id": "a", "face_a_id": "a", "face_b_id": "c", "part_a": "one", "part_b": "three", "plane_gap_mm": 0.1, "reason": "projected_aabb_no_overlap"},
    ]}
    faces = [_face("a", "one"), _face("b", "two", x0=20, x1=30), _face("c", "three", x0=10, x1=20)]
    measurements = iter([
        ExactPairMeasurement(0, .1, 0, 0, 0, 100, 100, "zero_area_intersection"),
        ExactPairMeasurement(0, .1, 2, .2, .2, 10, 10),
    ])
    report = diagnose_projected_aabb_rejections(audit, faces, exact_overlap=lambda *_: next(measurements))
    assert [row["pair_id"] for row in report["pairs"]] == ["a", "z"]
    assert [row["review_status"] for row in report["pairs"]] == ["true_no_overlap", "prefilter_false_rejection"]
    assert report["production_behavior_changed"] is False


def test_aabb_diagnosis_marks_insufficient_vertices_and_projection_failures():
    audit = {"pairs": [{"id": "pair", "face_a_id": "a", "face_b_id": "b", "reason": "projected_aabb_no_overlap"}]}
    face_a = _face("a", "one")
    face_b = _face("b", "two")
    face_b = face_b.__class__(**{**face_b.__dict__, "vertices": ()})
    report = diagnose_projected_aabb_rejections(
        audit, [face_a, face_b], exact_overlap=lambda *_: ExactPairMeasurement(0, 0, 0, 0, 0, 0, 0, "projection_failed:RuntimeError")
    )
    row = report["pairs"][0]
    assert row["prefilter_input_status"] == "insufficient_vertices"
    assert row["review_status"] == "projection_or_geometry_failure"


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


def test_expanded_gap_fp_attribution_marks_inherited_and_new_with_pair_provenance():
    baseline_evaluation, baseline_pairs, baseline_selection = _artifacts()
    baseline_pairs["pairs"][0].update({"part_a": "truth-part", "part_b": "extra-part"})
    baseline_selection["parameters"] = {"max_plane_gap_mm": 0.2, "allow_same_part_pairs": False}
    candidate_evaluation, candidate_pairs, candidate_selection = _artifacts()
    candidate_evaluation["false_positive_faces"].append({"face_id": "new-extra"})
    candidate_evaluation["summary"]["false_positives"] = 2
    candidate_pairs["pairs"][0].update({
        "part_a": "truth-part", "part_b": "extra-part", "gap_layer": "strict", "common_area_mm2": 12.0,
        "coverage_a": .8, "coverage_b": .7, "score": 6.72,
    })
    candidate_pairs["pairs"].append({
        "id": "accepted-new", "face_a_id": "new-extra", "face_b_id": "truth-selected", "accepted": True,
        "part_a": "new-part", "part_b": "truth-part", "gap_layer": "extended", "common_area_mm2": 4.0,
        "coverage_a": .2, "coverage_b": .9, "score": .72,
    })
    candidate_selection["parameters"] = {"max_plane_gap_mm": 1.5, "allow_same_part_pairs": False}
    candidate_selection["selected_faces"].append({"face_id": "new-extra", "supporting_pair_ids": ["accepted-new"]})
    candidate_selection["selected_face_count"] = 3
    candidate_selection["total_planar_faces"] = 6
    candidate_selection["rejected_faces"].append({"face_id": "other-rejected-2", "reason": "no_accepted_pair"})

    report = build_expanded_gap_false_positive_attribution(
        join_error_analysis(baseline_evaluation, baseline_pairs, baseline_selection),
        join_error_analysis(candidate_evaluation, candidate_pairs, candidate_selection),
    )

    assert report["comparison"].get("baseline_false_positives") == 1
    assert report["comparison"].get("candidate_false_positives") == 2
    assert report["comparison"].get("inherited_false_positives") == 1
    assert [row["attribution"] for row in report["false_positives"]] == ["inherited", "new"]
    new_support = report["false_positives"][1]["supporting_pairs"][0]
    assert new_support["gap_layer"] == "extended"
    assert new_support["counterpart_part"] == "truth-part"
    assert new_support["counterpart_truth_relation"] == "offline_truth_face"
    assert "| extra-selected | inherited |" in render_expanded_gap_false_positive_attribution_markdown(report)


def test_report_ranks_fn_reasons_and_makes_gap_the_first_recommendation():
    evaluation, pair_audit, selection_audit = _artifacts()
    pair_audit["pairs"][1].update({"reason": "plane_gap_exceeds_threshold", "part_a": "one", "part_b": "two"})

    report = build_error_analysis_report(join_error_analysis(evaluation, pair_audit, selection_audit), pair_audit)
    markdown = render_error_analysis_markdown(report)

    assert report["summary"] == evaluation["summary"]
    assert report["false_negative_reason_ranking"] == [
        {
            "failure_stage": "plane_gap",
            "count": 1,
            "recommended_direction": "Investigate a larger or layered plane-gap strategy before changing production defaults.",
        }
    ]
    assert report["optimization_priority"][:2] == ["plane_gap_strategy", "projected_aabb_diagnosis"]
    assert "| 1 | plane_gap | 1 |" in markdown
    assert "This report does not change production selection parameters." in markdown
    assert "## Metric definitions" in markdown
    assert "**TP (true positive):**" in markdown
    assert "## Summary" in markdown
    assert "The main error source is `plane_gap` (1 of 1 false negatives)." in markdown


def test_sweep_generates_complete_fixed_28_case_matrix_without_changing_defaults():
    default_params = {
        "max_normal_angle_deg": 0.5,
        "min_overlap_area_mm2": 1.0,
        "min_effective_width_mm": 0.1,
    }

    def evaluate_case(params):
        return {
            "summary": {
                "predicted_faces": 10,
                "truth_faces": 8,
                "true_positives": 7,
                "false_positives": 3,
                "false_negatives": 1,
                "precision": 0.7,
                "recall": 0.875,
                "passed": True,
            }
        }

    report = build_controlled_parameter_sweep(evaluate_case)

    assert report["scope"] == "offline_evaluation_only"
    assert report["case_count"] == 28
    assert len(report["cases"]) == 28
    assert {case["parameters"]["max_plane_gap_mm"] for case in report["cases"]} == {0.2, 0.3, 0.5, 0.8, 1.0, 1.5, 3.0}
    assert all(case["parameters"].items() >= default_params.items() for case in report["cases"])
    assert "| Gap (mm) |" in render_controlled_parameter_sweep_markdown(report)


def test_backlog_orders_gap_aabb_and_same_part_with_required_evidence_and_risk():
    error_report = {
        "scope": "offline_evaluation_only",
        "false_negative_reason_ranking": [
            {"failure_stage": "plane_gap", "count": 18},
            {"failure_stage": "projected_aabb", "count": 3},
            {"failure_stage": "same_part_policy", "count": 2},
        ],
    }
    sweep_report = build_controlled_parameter_sweep(
        lambda _params: {
            "summary": {
                "predicted_faces": 10, "truth_faces": 8, "true_positives": 7,
                "false_positives": 3, "false_negatives": 1, "precision": 0.7,
                "recall": 0.875, "passed": True,
            }
        }
    )

    backlog = build_optimization_recommendation_backlog(error_report, sweep_report)

    assert backlog["scope"] == "offline_planning_only"
    assert [row["target_error_cluster"] for row in backlog["recommendations"]] == [
        "plane_gap", "projected_aabb", "same_part_policy"
    ]
    assert all(row["evidence"] and row["precision_risk"] and row["acceptance_tests"] for row in backlog["recommendations"])


def test_same_part_risk_report_isolates_the_high_false_positive_offline_case():
    sweep = build_controlled_parameter_sweep(
        lambda params: {"summary": {
            "predicted_faces": 212 if params.allow_same_part_pairs else 36,
            "truth_faces": 40,
            "true_positives": 40 if params.allow_same_part_pairs else 30,
            "false_positives": 172 if params.allow_same_part_pairs else 6,
            "false_negatives": 0 if params.allow_same_part_pairs else 10,
            "precision": 40 / 212 if params.allow_same_part_pairs else 30 / 36,
            "recall": 1.0 if params.allow_same_part_pairs else .75,
            "passed": True,
        }}
    )
    report = build_same_part_risk_report(sweep)
    enabled = report["comparison"]["same_part_enabled_offline_only"]["summary"]
    assert report["production_guardrail"] == {"allow_same_part_pairs": False}
    assert (enabled["true_positives"], enabled["false_positives"], enabled["false_negatives"]) == (40, 172, 0)
    assert "Same-part pairs remain disabled in production." in render_same_part_risk_markdown(report)
