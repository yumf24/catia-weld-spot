"""Evaluate frozen template selections against the one-time reference STEP.

This module deliberately works with OCCT faces, not projected bounding boxes.
The reference STEP is only consumed by this evaluation path.
"""

from __future__ import annotations

from typing import Iterable

from .exact_face_overlap import CoplanarFacePair, exact_face_overlap
from .geometry import normal_angle_deg, point_to_plane_distance
from .plane_reference_labels import IndexedStepFace, MIN_SOURCE_COVERAGE


def _candidate(source: IndexedStepFace, reference: IndexedStepFace) -> dict:
    angle = normal_angle_deg(source.face.normal, reference.face.normal)
    distance = abs(point_to_plane_distance(reference.face.centroid, source.face.centroid, source.face.normal))
    overlap = exact_face_overlap(CoplanarFacePair(source.face.shape, reference.face.shape, angle, distance))
    return {
        "source_face_id": source.id,
        "source_face_index": source.index,
        "normal_angle_deg": angle,
        "plane_distance_mm": distance,
        "common_area_mm2": overlap.common_area_mm2,
        "source_coverage": overlap.source_coverage,
        "reference_coverage": overlap.reference_coverage,
        "reason": overlap.reason,
        "accepted": overlap.matched and overlap.source_coverage >= MIN_SOURCE_COVERAGE,
    }


def evaluate_plane_selection(
    selected_faces: Iterable[IndexedStepFace], reference_faces: Iterable[IndexedStepFace]
) -> dict:
    """Return exact TP/FP/FN metrics and per-reference geometric evidence."""
    selected = list(selected_faces)
    references = list(reference_faces)
    selected_hits = {face.id: [] for face in selected}
    rows: list[dict] = []
    for reference in references:
        candidates = [_candidate(source, reference) for source in selected if source.part == reference.part]
        accepted = [candidate for candidate in candidates if candidate["accepted"]]
        status = "matched" if len(accepted) == 1 else "unmatched" if not accepted else "ambiguous"
        reason = None if status == "matched" else (
            "no_selected_face_with_required_source_coverage" if status == "unmatched" else "ambiguous_selected_face_match"
        )
        if status == "matched":
            selected_hits[accepted[0]["source_face_id"]].append(reference.id)
        rows.append({
            "reference_face_id": reference.id,
            "reference_face_index": reference.index,
            "part": reference.part,
            "status": status,
            "reason": reason,
            "matched_source_face_id": accepted[0]["source_face_id"] if status == "matched" else None,
            "candidates": candidates,
        })
    tp = [face for face in selected if selected_hits[face.id]]
    fp = [face for face in selected if not selected_hits[face.id]]
    fn = [row for row in rows if row["status"] != "matched"]
    precision = len(tp) / len(selected) if selected else 0.0
    recall = (len(references) - len(fn)) / len(references) if references else 0.0
    return {
        "format_version": 1,
        "thresholds": {"normal_angle_deg_max": 0.5, "plane_distance_mm_max": 0.05,
                       "source_coverage_min": MIN_SOURCE_COVERAGE},
        "summary": {
            "selected_faces": len(selected), "reference_faces": len(references),
            "true_positives": len(tp), "false_positives": len(fp), "false_negatives": len(fn),
            "precision": precision, "recall": recall,
            "passed": precision > 0.90 and recall > 0.95,
        },
        "selected_faces": [
            {"face_id": face.id, "part": face.part, "step_face_index": face.index,
             "status": "true_positive" if selected_hits[face.id] else "false_positive",
             "matched_reference_faces": selected_hits[face.id]}
            for face in selected
        ],
        "reference_faces": rows,
        "false_positive_faces": [face.id for face in fp],
        "false_negative_faces": [row["reference_face_id"] for row in fn],
    }


def evaluation_markdown(result: dict) -> str:
    """Render a compact human-readable companion to the JSON audit."""
    summary = result["summary"]
    return "\n".join([
        "# Exact plane selection evaluation", "",
        f"- TP / FP / FN: {summary['true_positives']} / {summary['false_positives']} / {summary['false_negatives']}",
        f"- Precision: {summary['precision']:.2%}", f"- Recall: {summary['recall']:.2%}",
        f"- Passed: {summary['passed']}", "",
        "All match decisions use OCCT common CAD-face area and the recorded normal, plane-distance, and coverage thresholds.", "",
    ])
