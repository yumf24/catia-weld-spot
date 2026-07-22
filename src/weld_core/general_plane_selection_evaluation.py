"""Offline evaluation for generic planar face selection.

Reference faces are accepted only as explicit inputs to this module.  The
runtime selector never imports this module, and no truth labels produced here
are part of the production selection contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .general_plane_selection import GeneralPlaneFace, exact_projected_pair_overlap
from .geometry import normal_angle_deg, point_to_plane_distance


@dataclass(frozen=True)
class GeneralSelectionEvaluationThresholds:
    normal_angle_deg_max: float = 0.5
    plane_distance_mm_max: float = 0.05
    reference_mapping_source_coverage_min: float = 0.95
    reference_mapping_reference_coverage_min: float = 0.95


def _candidate(source: GeneralPlaneFace, reference: GeneralPlaneFace, thresholds: GeneralSelectionEvaluationThresholds) -> dict:
    angle = normal_angle_deg(source.normal, reference.normal)
    distance = abs(point_to_plane_distance(reference.plane_origin, source.plane_origin, source.normal))
    if angle > thresholds.normal_angle_deg_max:
        return {
            "source_face_id": source.id,
            "normal_angle_deg": angle,
            "plane_distance_mm": distance,
            "common_area_mm2": 0.0,
            "source_coverage": 0.0,
            "reference_coverage": 0.0,
            "accepted": False,
            "reason": "normal_angle_exceeds_threshold",
        }
    if distance > thresholds.plane_distance_mm_max:
        return {
            "source_face_id": source.id,
            "normal_angle_deg": angle,
            "plane_distance_mm": distance,
            "common_area_mm2": 0.0,
            "source_coverage": 0.0,
            "reference_coverage": 0.0,
            "accepted": False,
            "reason": "plane_distance_exceeds_threshold",
        }
    overlap = exact_projected_pair_overlap(source, reference, normal_angle_deg_value=angle, plane_gap_mm_value=distance)
    reason = overlap.reason
    if not reason and overlap.coverage_a < thresholds.reference_mapping_source_coverage_min:
        reason = "source_coverage_below_threshold"
    if not reason and overlap.coverage_b < thresholds.reference_mapping_reference_coverage_min:
        reason = "reference_coverage_below_threshold"
    return {
        "source_face_id": source.id,
        "normal_angle_deg": overlap.normal_angle_deg,
        "plane_distance_mm": overlap.plane_gap_mm,
        "common_area_mm2": overlap.common_area_mm2,
        "source_coverage": overlap.coverage_a,
        "reference_coverage": overlap.coverage_b,
        "accepted": reason is None,
        "reason": reason,
    }


def build_offline_truth_mapping(
    source_faces: Iterable[GeneralPlaneFace],
    reference_faces: Iterable[GeneralPlaneFace],
    thresholds: GeneralSelectionEvaluationThresholds = GeneralSelectionEvaluationThresholds(),
) -> dict:
    """Map each explicit reference face to one source CAD face, or fail audibly."""

    sources = list(source_faces)
    references = list(reference_faces)
    reference_rows: list[dict] = []
    mapped_source_ids: list[str] = []
    for reference in references:
        candidates = [
            _candidate(source, reference, thresholds)
            for source in sources
            if source.part == reference.part
        ]
        accepted = [candidate for candidate in candidates if candidate["accepted"]]
        status = "mapped" if len(accepted) == 1 else "unmapped" if not accepted else "ambiguous"
        reason = None
        if status == "unmapped":
            reason = "no_unique_source_face_with_required_coverage"
        elif status == "ambiguous":
            reason = "ambiguous_multiple_source_faces"
        if status == "mapped":
            mapped_source_ids.append(accepted[0]["source_face_id"])
        reference_rows.append({
            "reference_face_id": reference.id,
            "part": reference.part,
            "status": status,
            "reason": reason,
            "mapped_source_face_id": accepted[0]["source_face_id"] if status == "mapped" else None,
            "candidates": candidates,
        })
    return {
        "thresholds": {
            "normal_angle_deg_max": thresholds.normal_angle_deg_max,
            "plane_distance_mm_max": thresholds.plane_distance_mm_max,
            "reference_mapping_source_coverage_min": thresholds.reference_mapping_source_coverage_min,
            "reference_mapping_reference_coverage_min": thresholds.reference_mapping_reference_coverage_min,
        },
        "summary": {
            "source_faces": len(sources),
            "reference_faces": len(references),
            "mapped_reference_faces": sum(row["status"] == "mapped" for row in reference_rows),
            "failed_reference_faces": sum(row["status"] != "mapped" for row in reference_rows),
            "passed": all(row["status"] == "mapped" for row in reference_rows),
        },
        "truth_face_ids": sorted(set(mapped_source_ids)),
        "reference_faces": reference_rows,
    }


def evaluate_general_plane_selection(
    source_faces: Iterable[GeneralPlaneFace],
    reference_faces: Iterable[GeneralPlaneFace],
    predicted_face_ids: Iterable[str],
    thresholds: GeneralSelectionEvaluationThresholds = GeneralSelectionEvaluationThresholds(),
) -> dict:
    """Evaluate predicted source face ids against explicit offline references."""

    sources = list(source_faces)
    source_ids = {face.id for face in sources}
    predicted = sorted(set(predicted_face_ids))
    truth_mapping = build_offline_truth_mapping(sources, list(reference_faces), thresholds)
    truth_ids = set(truth_mapping["truth_face_ids"]) if truth_mapping["summary"]["passed"] else set()
    predicted_ids = set(predicted)
    true_positive_ids = sorted(predicted_ids & truth_ids)
    false_positive_ids = sorted(predicted_ids - truth_ids)
    false_negative_ids = sorted(truth_ids - predicted_ids)
    unknown_prediction_ids = sorted(predicted_ids - source_ids)
    precision = len(true_positive_ids) / len(predicted_ids) if predicted_ids else 0.0
    recall = len(true_positive_ids) / len(truth_ids) if truth_ids else 0.0
    return {
        "format_version": 1,
        "thresholds": truth_mapping["thresholds"],
        "truth_mapping": truth_mapping,
        "summary": {
            "source_faces": len(sources),
            "predicted_faces": len(predicted_ids),
            "truth_faces": len(truth_ids),
            "true_positives": len(true_positive_ids),
            "false_positives": len(false_positive_ids),
            "false_negatives": len(false_negative_ids),
            "precision": precision,
            "recall": recall,
            "passed": truth_mapping["summary"]["passed"],
        },
        "true_positive_faces": [
            {"face_id": face_id, "reason": "predicted_face_matches_offline_truth"}
            for face_id in true_positive_ids
        ],
        "false_positive_faces": [
            {
                "face_id": face_id,
                "reason": "unknown_predicted_face" if face_id in unknown_prediction_ids else "predicted_face_not_in_offline_truth",
            }
            for face_id in false_positive_ids
        ],
        "false_negative_faces": [
            {"face_id": face_id, "reason": "truth_face_not_predicted"}
            for face_id in false_negative_ids
        ],
    }


def evaluation_markdown(result: dict) -> str:
    """Render a compact Markdown companion for the JSON evaluation."""

    summary = result["summary"]
    return "\n".join([
        "# General plane selection evaluation",
        "",
        f"- TP / FP / FN: {summary['true_positives']} / {summary['false_positives']} / {summary['false_negatives']}",
        f"- Precision: {summary['precision']:.2%}",
        f"- Recall: {summary['recall']:.2%}",
        f"- Truth mapping passed: {summary['passed']}",
        "",
        "All truth mapping is built from explicit offline reference faces and exact projected CAD-face overlap.",
        "",
    ])
