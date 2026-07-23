"""Offline review of generic-selector projected-AABB rejections.

This module intentionally is not used by the selector or pipeline.  It
replays only already-recorded ``projected_aabb_no_overlap`` pairs against the
registered primary CAD geometry, bypassing the inexpensive vertex-AABB
pre-filter to establish whether the rejection was geometrically justified.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .general_plane_selection import (
    ExactPairMeasurement,
    GeneralPlaneFace,
    exact_projected_pair_overlap,
)


_GEOMETRY_FAILURE_PREFIXES = ("projection_failed:", "boolean_common_failed:", "zero_area_input")


def _prefilter_input_status(face_a: GeneralPlaneFace, face_b: GeneralPlaneFace) -> str:
    if len(face_a.vertices) < 3 or len(face_b.vertices) < 3:
        return "insufficient_vertices"
    return "no_positive_projected_aabb_overlap"


def _review_status(measurement: ExactPairMeasurement) -> str:
    if measurement.reason and measurement.reason.startswith(_GEOMETRY_FAILURE_PREFIXES):
        return "projection_or_geometry_failure"
    if measurement.common_area_mm2 > 0.0:
        return "prefilter_false_rejection"
    return "true_no_overlap"


def diagnose_projected_aabb_rejections(
    pair_audit: dict[str, Any],
    faces: Iterable[GeneralPlaneFace],
    *,
    exact_overlap: Callable[[GeneralPlaneFace, GeneralPlaneFace], ExactPairMeasurement] = exact_projected_pair_overlap,
) -> dict[str, Any]:
    """Return stable offline exact-overlap reviews for AABB-rejected pairs.

    Missing endpoints indicate that the audit cannot be reliably replayed and
    are reported as a geometry-review failure rather than silently omitted.
    """

    faces_by_id = {face.id: face for face in faces}
    reviews: list[dict[str, Any]] = []
    rejected_pairs = sorted(
        (pair for pair in pair_audit.get("pairs", []) if pair.get("reason") == "projected_aabb_no_overlap"),
        key=lambda pair: str(pair.get("id", "")),
    )
    for pair in rejected_pairs:
        face_a = faces_by_id.get(pair.get("face_a_id"))
        face_b = faces_by_id.get(pair.get("face_b_id"))
        base = {
            "pair_id": pair.get("id"),
            "face_a_id": pair.get("face_a_id"),
            "face_b_id": pair.get("face_b_id"),
            "part_a": pair.get("part_a"),
            "part_b": pair.get("part_b"),
            "plane_gap_mm": pair.get("plane_gap_mm"),
        }
        if face_a is None or face_b is None:
            reviews.append(
                {
                    **base,
                    "prefilter_input_status": "face_not_reloaded",
                    "exact_common_area_mm2": 0.0,
                    "exact_coverage_a": 0.0,
                    "exact_coverage_b": 0.0,
                    "exact_reason": "face_not_reloaded",
                    "review_status": "projection_or_geometry_failure",
                }
            )
            continue
        try:
            measurement = exact_overlap(face_a, face_b)
        except Exception as exc:  # Allows diagnostics to report unexpected geometry API failures.
            measurement = ExactPairMeasurement(0.0, base["plane_gap_mm"] or 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, f"projection_failed:{type(exc).__name__}")
        reviews.append(
            {
                **base,
                "prefilter_input_status": _prefilter_input_status(face_a, face_b),
                "exact_common_area_mm2": measurement.common_area_mm2,
                "exact_coverage_a": measurement.coverage_a,
                "exact_coverage_b": measurement.coverage_b,
                "exact_reason": measurement.reason,
                "review_status": _review_status(measurement),
            }
        )
    counts = {status: sum(row["review_status"] == status for row in reviews) for status in (
        "true_no_overlap", "prefilter_false_rejection", "projection_or_geometry_failure",
    )}
    return {
        "format_version": 1,
        "scope": "offline_aabb_pre_filter_diagnosis",
        "production_behavior_changed": False,
        "review_count": len(reviews),
        "review_status_counts": counts,
        "pairs": reviews,
    }
