"""Offline exact-overlap replay for cross-part plane-gap rejections.

This module is intentionally outside the production selector and pipeline.  It
uses the evaluation result only to state a theoretical recovery ceiling after
the geometric replay has completed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .general_plane_selection import (
    ExactPairMeasurement,
    GeneralPlaneFace,
    GeneralSelectionParams,
    _projected_aabb_overlap,
    exact_projected_pair_overlap,
)


_GAP_TIERS = ((1.5, 3.0, "1.5-3"), (3.0, 4.5, "3-4.5"), (4.5, 6.0, "4.5-6"))


def _tier(gap_mm: float) -> str:
    for lower, upper, name in _GAP_TIERS:
        if lower < gap_mm <= upper:
            return name
    raise ValueError(f"gap {gap_mm} is outside the managed 1.5-6 mm diagnosis range")


def _recovery_reason(measurement: ExactPairMeasurement, effective_width_mm: float, params: GeneralSelectionParams) -> str | None:
    if measurement.reason is not None:
        return measurement.reason
    if measurement.common_area_mm2 <= 0.0:
        return "exact_overlap_not_positive"
    if measurement.common_area_mm2 < params.min_overlap_area_mm2:
        return "overlap_area_below_threshold"
    if min(measurement.coverage_a, measurement.coverage_b) < params.min_face_coverage:
        return "coverage_below_threshold"
    if effective_width_mm < params.min_effective_width_mm:
        return "effective_width_below_threshold"
    return None


def diagnose_gap_recovery(
    pair_audit: dict[str, Any],
    faces: Iterable[GeneralPlaneFace],
    *,
    baseline_true_positives: int,
    false_negative_face_ids: Iterable[str],
    aabb_prefilter_false_rejection_count: int,
    params: GeneralSelectionParams = GeneralSelectionParams(),
    exact_overlap: Callable[[GeneralPlaneFace, GeneralPlaneFace], ExactPairMeasurement] = exact_projected_pair_overlap,
    projected_aabb_overlap: Callable[[GeneralPlaneFace, GeneralPlaneFace], tuple[float, float] | None] = _projected_aabb_overlap,
) -> dict[str, Any]:
    """Replay managed 1.5--6 mm cross-part gap rejections deterministically.

    The exact measurement is always made before retaining projected-width data.
    AABB is never a recovery fallback; its independently diagnosed false-
    rejection count is recorded as a fixed production-boundary precondition.
    """

    if aabb_prefilter_false_rejection_count != 0:
        raise ValueError("gap recovery requires zero AABB prefilter false rejections")
    faces_by_id = {face.id: face for face in faces}
    false_negatives = set(false_negative_face_ids)
    candidates = sorted(
        (
            pair for pair in pair_audit.get("pairs", [])
            if pair.get("reason") == "plane_gap_exceeds_threshold"
            and pair.get("part_a") != pair.get("part_b")
            and isinstance(pair.get("plane_gap_mm"), (int, float))
            and 1.5 < pair["plane_gap_mm"] <= 6.0
        ),
        key=lambda pair: str(pair.get("id", "")),
    )
    rows: list[dict[str, Any]] = []
    recovered_false_negatives: set[str] = set()
    for pair in candidates:
        face_a = faces_by_id.get(pair.get("face_a_id"))
        face_b = faces_by_id.get(pair.get("face_b_id"))
        if face_a is None or face_b is None:
            measurement = ExactPairMeasurement(0.0, float(pair["plane_gap_mm"]), 0.0, 0.0, 0.0, 0.0, 0.0, "face_not_reloaded")
            width = 0.0
        else:
            measurement = exact_overlap(face_a, face_b)
            overlap = projected_aabb_overlap(face_a, face_b)
            width = min(overlap) if overlap is not None else 0.0
        reason = _recovery_reason(measurement, width, params)
        recovered = reason is None
        endpoints = {str(pair.get("face_a_id")), str(pair.get("face_b_id"))}
        recovered_false_negatives.update(endpoints & false_negatives if recovered else set())
        score = measurement.common_area_mm2 * min(measurement.coverage_a, measurement.coverage_b) if recovered else 0.0
        rows.append({
            "pair_id": pair.get("id"), "face_a_id": pair.get("face_a_id"), "face_b_id": pair.get("face_b_id"),
            "part_a": pair.get("part_a"), "part_b": pair.get("part_b"), "gap_mm": pair["plane_gap_mm"],
            "gap_tier": _tier(float(pair["plane_gap_mm"])), "exact_common_area_mm2": measurement.common_area_mm2,
            "exact_coverage_a": measurement.coverage_a, "exact_coverage_b": measurement.coverage_b,
            "effective_width_mm": width, "score": score, "exact_reason": measurement.reason,
            "recovery_reason": reason, "recovery_status": "recoverable" if recovered else "not_recoverable",
            "touches_offline_false_negative": bool(endpoints & false_negatives),
        })
    theoretical_upper_tp = baseline_true_positives + len(recovered_false_negatives)
    return {
        "format_version": 1, "scope": "offline_gap_recovery_diagnosis", "production_behavior_changed": False,
        "aabb_prefilter_false_rejection_count": aabb_prefilter_false_rejection_count,
        "gap_tiers_mm": [{"name": name, "lower_exclusive": lower, "upper_inclusive": upper} for lower, upper, name in _GAP_TIERS],
        "review_count": len(rows), "pairs": rows,
        "theoretical_recoverable_false_negative_count": len(recovered_false_negatives),
        "theoretical_upper_true_positives": theoretical_upper_tp,
        "target_true_positives": 37, "target_geometrically_feasible": theoretical_upper_tp >= 37,
        "target_unreachable_under_fixed_boundaries": theoretical_upper_tp < 37,
    }
