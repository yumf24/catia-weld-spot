"""Offline-only controlled same-part pair topology diagnosis.

This module is deliberately not imported by the production selector or
candidate pipeline.  It replays registered primary-model geometry and uses
offline truth only after geometric/topological measurements are complete.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from itertools import combinations
from typing import Any

from OCP.TopAbs import TopAbs_EDGE, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer

from .general_plane_selection import (
    ExactPairMeasurement,
    GeneralPlaneFace,
    GeneralSelectionParams,
    _projected_aabb_overlap,
    exact_projected_pair_overlap,
)
from .geometry import normal_angle_deg, point_to_plane_distance


_TOPOLOGY_CLASSES = (
    "shared_edge",
    "shared_vertex_only",
    "disjoint_boundaries",
    "topology_unknown",
)


def _boundary_shapes(shape: Any, kind: Any) -> tuple[Any, ...]:
    explorer = TopExp_Explorer(shape, kind)
    boundaries: list[Any] = []
    while explorer.More():
        boundaries.append(explorer.Current())
        explorer.Next()
    return tuple(boundaries)


def classify_same_part_topology(face_a: GeneralPlaneFace, face_b: GeneralPlaneFace) -> str:
    """Classify shared OCCT face boundaries without labels or face IDs.

    ``TopoDS_Shape.IsSame`` compares the OCCT topological identity (including
    location), so this is deterministic, symmetric, and does not use body,
    part, assembly, or dataset metadata as a policy feature.
    """

    if face_a.shape is None or face_b.shape is None:
        return "topology_unknown"
    try:
        edges_a = _boundary_shapes(face_a.shape, TopAbs_EDGE)
        edges_b = _boundary_shapes(face_b.shape, TopAbs_EDGE)
        if any(edge_a.IsSame(edge_b) for edge_a in edges_a for edge_b in edges_b):
            return "shared_edge"
        vertices_a = _boundary_shapes(face_a.shape, TopAbs_VERTEX)
        vertices_b = _boundary_shapes(face_b.shape, TopAbs_VERTEX)
        if any(vertex_a.IsSame(vertex_b) for vertex_a in vertices_a for vertex_b in vertices_b):
            return "shared_vertex_only"
        return "disjoint_boundaries"
    except Exception:
        return "topology_unknown"


def _recovery_reason(measurement: ExactPairMeasurement, width: float, params: GeneralSelectionParams) -> str | None:
    if measurement.reason is not None:
        return measurement.reason
    if measurement.common_area_mm2 <= 0.0:
        return "exact_overlap_not_positive"
    if measurement.common_area_mm2 < params.min_overlap_area_mm2:
        return "overlap_area_below_threshold"
    if min(measurement.coverage_a, measurement.coverage_b) < params.min_face_coverage:
        return "coverage_below_threshold"
    if width < params.min_effective_width_mm:
        return "effective_width_below_threshold"
    return None


def _face_composition(face_ids: set[str], truth: set[str], predicted: set[str]) -> dict[str, int]:
    return {
        "true_positives": len(face_ids & truth & predicted),
        "false_positives": len(face_ids - truth),
        "false_negatives": len(face_ids & truth - predicted),
    }


def diagnose_same_part_topology(
    faces: Iterable[GeneralPlaneFace],
    *,
    baseline_true_positives: int,
    offline_truth_face_ids: Iterable[str],
    baseline_predicted_face_ids: Iterable[str],
    params: GeneralSelectionParams = GeneralSelectionParams(),
    exact_overlap: Callable[[GeneralPlaneFace, GeneralPlaneFace], ExactPairMeasurement] = exact_projected_pair_overlap,
    projected_aabb_overlap: Callable[[GeneralPlaneFace, GeneralPlaneFace], tuple[float, float] | None] = _projected_aabb_overlap,
    topology_classifier: Callable[[GeneralPlaneFace, GeneralPlaneFace], str] = classify_same_part_topology,
) -> dict[str, Any]:
    """Replay all same-part pairs in the fixed normal/gap bounds once.

    No selection decision is produced.  The report exposes every reviewed pair
    for future offline policy search, while the truth-derived summary remains
    clearly evaluation-only.
    """

    truth = set(offline_truth_face_ids)
    predicted = set(baseline_predicted_face_ids)
    by_part: dict[str, list[GeneralPlaneFace]] = defaultdict(list)
    for face in faces:
        by_part[face.part].append(face)

    rows: list[dict[str, Any]] = []
    valid_faces_by_topology: dict[str, set[str]] = {name: set() for name in _TOPOLOGY_CLASSES}
    recoverable_false_negatives: set[str] = set()
    for part in sorted(by_part):
        for face_a, face_b in combinations(sorted(by_part[part], key=lambda face: face.id), 2):
            angle = normal_angle_deg(face_a.normal, face_b.normal)
            if angle > params.max_normal_angle_deg:
                continue
            gap = abs(point_to_plane_distance(face_b.plane_origin, face_a.plane_origin, face_a.normal))
            if gap > params.max_plane_gap_mm:
                continue
            topology = topology_classifier(face_a, face_b)
            if topology not in _TOPOLOGY_CLASSES:
                raise ValueError(f"invalid topology classification: {topology!r}")
            try:
                measurement = exact_overlap(face_a, face_b)
            except Exception as exc:
                measurement = ExactPairMeasurement(angle, gap, 0.0, 0.0, 0.0, 0.0, 0.0, f"projection_failed:{type(exc).__name__}")
            overlap = projected_aabb_overlap(face_a, face_b)
            width = min(overlap) if overlap is not None else 0.0
            reason = _recovery_reason(measurement, width, params)
            exact_valid = reason is None
            endpoints = {face_a.id, face_b.id}
            if exact_valid:
                valid_faces_by_topology[topology].update(endpoints)
                recoverable_false_negatives.update(endpoints & truth - predicted)
            rows.append({
                "pair_id": f"{face_a.id}::{face_b.id}",
                "face_a_id": face_a.id,
                "face_b_id": face_b.id,
                "same_part_relation": "same_part",
                "topology_class": topology,
                "normal_angle_deg": measurement.normal_angle_deg,
                "gap_mm": measurement.plane_gap_mm,
                "exact_common_area_mm2": measurement.common_area_mm2,
                "exact_coverage_a": measurement.coverage_a,
                "exact_coverage_b": measurement.coverage_b,
                "effective_width_mm": width,
                "score": measurement.common_area_mm2 * min(measurement.coverage_a, measurement.coverage_b),
                "exact_reason": measurement.reason,
                "recovery_reason": reason,
                "recovery_status": "recoverable" if exact_valid else "not_recoverable",
            })

    rows.sort(key=lambda row: row["pair_id"])
    composition = {
        topology: _face_composition(valid_faces_by_topology[topology], truth, predicted)
        for topology in _TOPOLOGY_CLASSES
    }
    upper_tp = baseline_true_positives + len(recoverable_false_negatives)
    return {
        "format_version": 1,
        "scope": "offline_same_part_topology_diagnosis",
        "production_behavior_changed": False,
        "fixed_geometry_bounds": {
            "max_normal_angle_deg": params.max_normal_angle_deg,
            "max_plane_gap_mm": params.max_plane_gap_mm,
            "min_overlap_area_mm2": params.min_overlap_area_mm2,
            "min_face_coverage": params.min_face_coverage,
            "min_effective_width_mm": params.min_effective_width_mm,
        },
        "review_count": len(rows),
        "pairs": rows,
        "evaluation_only": {
            "face_composition_by_topology": composition,
            "same_part_false_negative_recovery_ceiling": len(recoverable_false_negatives),
            "theoretical_upper_true_positives": upper_tp,
            "target_true_positives": 37,
            "all_exact_valid_same_part_pairs_reach_target": upper_tp >= 37,
        },
    }


def render_same_part_topology_markdown(report: dict[str, Any]) -> str:
    """Render the managed human-readable companion without policy advice."""

    evaluation = report["evaluation_only"]
    lines = [
        "# Controlled Same-Part Topology Diagnosis",
        "",
        "Offline-only geometry/topology replay. Production behavior is unchanged: `allow_same_part_pairs=false`.",
        "",
        f"Reviewed pairs: {report['review_count']}",
        "",
        "## Evaluation-only topology composition",
        "",
        "| Topology | TP | FP | FN |",
        "| --- | ---: | ---: | ---: |",
    ]
    for topology, counts in evaluation["face_composition_by_topology"].items():
        lines.append(f"| {topology} | {counts['true_positives']} | {counts['false_positives']} | {counts['false_negatives']} |")
    lines.extend([
        "",
        f"Same-part FN recovery ceiling: {evaluation['same_part_false_negative_recovery_ceiling']}",
        f"Theoretical upper TP: {evaluation['theoretical_upper_true_positives']} (target: {evaluation['target_true_positives']})",
        f"All exact-valid same-part pairs reach target: {evaluation['all_exact_valid_same_part_pairs_reach_target']}",
        "",
        "Truth is used only for this report; it is not an input to production selection or policy generation.",
    ])
    return "\n".join(lines) + "\n"
