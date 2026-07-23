"""Offline-only controlled same-part pair topology diagnosis.

This module is deliberately not imported by the production selector or
candidate pipeline.  It replays registered primary-model geometry and uses
offline truth only after geometric/topological measurements are complete.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from itertools import combinations, product
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

_CONTROLLED_MIN_AREAS = (1.0, 5.0, 10.0, 25.0, 50.0, 100.0)
_CONTROLLED_MIN_COVERAGES = (0.05, 0.10, 0.20, 0.40, 0.60, 0.80)
_CONTROLLED_MIN_WIDTHS = (0.1, 1.0, 3.0, 5.0, 10.0)
_CONTROLLED_MIN_SCORES = (0.0, 1.0, 5.0, 10.0, 25.0, 50.0, 100.0)
_CONTROLLED_TOPOLOGY_RULES = ("no_constraint", "exclude_shared_edge", "disjoint_boundaries_only")


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


def build_controlled_same_part_conclusion(
    topology_diagnosis: dict[str, Any], policy_search: dict[str, Any]
) -> dict[str, Any]:
    """Summarize a completed controlled-pair search for offline review only.

    The inputs have already separated geometry/policy replay from the
    evaluation-only truth metrics.  This function merely publishes their
    deterministic result; it does not supply an input to production code.
    """

    if topology_diagnosis.get("scope") != "offline_same_part_topology_diagnosis":
        raise ValueError("invalid same-part topology diagnosis")
    if policy_search.get("scope") != "offline_controlled_pair_policy_search":
        raise ValueError("invalid controlled pair policy search")
    if topology_diagnosis.get("production_behavior_changed") is not False:
        raise ValueError("topology diagnosis must not change production behavior")
    if policy_search.get("production_behavior_changed") is not False:
        raise ValueError("policy search must not change production behavior")

    cases = policy_search.get("cases")
    if not isinstance(cases, list):
        raise ValueError("controlled pair policy search has no cases")
    strict_cases = [case for case in cases if case.get("passed") is True]
    selected = policy_search.get("selected_strict_pass_policy")
    if bool(selected) != bool(strict_cases):
        raise ValueError("selected strict policy does not match policy search pass state")

    evaluation = topology_diagnosis["evaluation_only"]
    outcome = "strict_pass_policy_selected" if selected else "no_feasible_policy"
    return {
        "format_version": 1,
        "scope": "offline_controlled_same_part_conclusion",
        "production_defaults_changed": False,
        "production_guardrail": {"allow_same_part_pairs": False},
        "generalization_boundary": (
            "Single-dataset offline regression evidence only; no independent validation "
            "parts are available and no cross-part generalization is claimed."
        ),
        "evaluation_only_inputs": {
            "reference_and_truth": True,
            "policy_generation_uses_reference_or_truth": False,
        },
        "topology_diagnosis": {
            "artifact_scope": topology_diagnosis["scope"],
            "review_count": topology_diagnosis["review_count"],
            "face_composition_by_topology": evaluation["face_composition_by_topology"],
            "same_part_false_negative_recovery_ceiling": evaluation["same_part_false_negative_recovery_ceiling"],
            "theoretical_upper_true_positives": evaluation["theoretical_upper_true_positives"],
            "target_true_positives": evaluation["target_true_positives"],
            "geometrically_feasible": evaluation["all_exact_valid_same_part_pairs_reach_target"],
        },
        "policy_search": {
            "artifact_scope": policy_search["scope"],
            "case_count": policy_search["case_count"],
            "quality_gate": policy_search["quality_gate"],
            "strict_pass_case_count": len(strict_cases),
            "selected_strict_pass_policy": selected,
            "ordering_evidence_artifact": "general_plane_selection_controlled_pair_policy_search.json",
        },
        "outcome": outcome,
        "conclusion": (
            "No policy in the fixed controlled-pair matrix passes the strict quality gate. "
            "Production same-part behavior remains disabled."
            if outcome == "no_feasible_policy"
            else "The selected policy is offline evidence only and does not change production behavior."
        ),
    }


def render_controlled_same_part_conclusion_markdown(report: dict[str, Any]) -> str:
    """Render the human-readable counterpart to the conclusion JSON."""

    topology = report["topology_diagnosis"]
    policy = report["policy_search"]
    lines = [
        "# Controlled Same-Part Offline Conclusion",
        "",
        f"Outcome: **{report['outcome']}**",
        "",
        "Production defaults are unchanged: `allow_same_part_pairs=false`.",
        "",
        "## Evidence",
        "",
        f"- Topology reviews: {topology['review_count']}",
        f"- Same-part FN recovery ceiling: {topology['same_part_false_negative_recovery_ceiling']}",
        f"- Theoretical upper TP: {topology['theoretical_upper_true_positives']} (target: {topology['target_true_positives']})",
        f"- Policy cases replayed: {policy['case_count']}",
        f"- Strict-pass policies: {policy['strict_pass_case_count']}",
        "",
        "The policy-search JSON contains the complete canonical ordering evidence for every case.",
        "Reference STEP and truth are evaluation-only inputs; policy generation and production selection do not consume them.",
        report["generalization_boundary"],
        "",
        report["conclusion"],
    ]
    return "\n".join(lines) + "\n"


def build_permissive_controlled_pair_audit(
    faces: Iterable[GeneralPlaneFace],
    *,
    params: GeneralSelectionParams = GeneralSelectionParams(),
    exact_overlap: Callable[[GeneralPlaneFace, GeneralPlaneFace], ExactPairMeasurement] = exact_projected_pair_overlap,
    projected_aabb_overlap: Callable[[GeneralPlaneFace, GeneralPlaneFace], tuple[float, float] | None] = _projected_aabb_overlap,
    topology_classifier: Callable[[GeneralPlaneFace, GeneralPlaneFace], str] = classify_same_part_topology,
) -> dict[str, Any]:
    """Measure each pair inside fixed angle/gap bounds exactly once, offline.

    This is a deliberately permissive geometry audit: projected AABB can
    record a terminal no-overlap rejection but can never accept a pair or
    substitute for exact geometry. Every eventual acceptance still requires
    a positive exact projected overlap; the positive extent also supplies the
    auditable effective-width measurement for replay.
    """

    rows: list[dict[str, Any]] = []
    ordered = sorted(faces, key=lambda face: face.id)
    for face_a, face_b in combinations(ordered, 2):
        angle = normal_angle_deg(face_a.normal, face_b.normal)
        if angle > params.max_normal_angle_deg:
            continue
        gap = abs(point_to_plane_distance(face_b.plane_origin, face_a.plane_origin, face_a.normal))
        if gap > params.max_plane_gap_mm:
            continue
        topology = "not_same_part"
        if face_a.part == face_b.part:
            topology = topology_classifier(face_a, face_b)
            if topology not in _TOPOLOGY_CLASSES:
                raise ValueError(f"invalid topology classification: {topology!r}")
        extent = projected_aabb_overlap(face_a, face_b)
        width = min(extent) if extent is not None else 0.0
        if extent is None:
            # This is a terminal geometry-audit rejection, never an
            # acceptance shortcut or an exact-overlap fallback.
            measurement = ExactPairMeasurement(angle, gap, 0.0, 0.0, 0.0, 0.0, 0.0, "projected_aabb_no_overlap")
        else:
            try:
                measurement = exact_overlap(face_a, face_b)
            except Exception as exc:
                measurement = ExactPairMeasurement(angle, gap, 0.0, 0.0, 0.0, 0.0, 0.0, f"projection_failed:{type(exc).__name__}")
        rows.append({
            "pair_id": f"{face_a.id}::{face_b.id}",
            "face_a_id": face_a.id,
            "face_b_id": face_b.id,
            "same_part_relation": "same_part" if face_a.part == face_b.part else "different_parts",
            "topology_class": topology,
            "normal_angle_deg": measurement.normal_angle_deg,
            "gap_mm": measurement.plane_gap_mm,
            "exact_common_area_mm2": measurement.common_area_mm2,
            "exact_coverage_a": measurement.coverage_a,
            "exact_coverage_b": measurement.coverage_b,
            "effective_width_mm": width,
            "score": measurement.common_area_mm2 * min(measurement.coverage_a, measurement.coverage_b),
            "exact_reason": measurement.reason,
        })
    return {
        "format_version": 1,
        "scope": "offline_controlled_pair_geometry_audit",
        "production_behavior_changed": False,
        "fixed_geometry_bounds": {"max_normal_angle_deg": params.max_normal_angle_deg, "max_plane_gap_mm": params.max_plane_gap_mm},
        "pair_count": len(rows),
        "pairs": rows,
    }


def _controlled_policy_cases() -> Iterable[dict[str, Any]]:
    for area, coverage, width, score, topology in product(
        _CONTROLLED_MIN_AREAS, _CONTROLLED_MIN_COVERAGES, _CONTROLLED_MIN_WIDTHS,
        _CONTROLLED_MIN_SCORES, _CONTROLLED_TOPOLOGY_RULES,
    ):
        yield dict(sorted({
            "max_normal_angle_deg": 0.5, "max_plane_gap_mm": 1.5,
            "min_overlap_area_mm2": area, "min_face_coverage": coverage,
            "min_effective_width_mm": width, "min_score": score,
            "same_part_topology": topology,
        }.items()))


def _replay_pair(row: dict[str, Any], policy: dict[str, Any]) -> str | None:
    if row["exact_reason"] is not None or row["exact_common_area_mm2"] <= 0.0:
        return "exact_overlap_not_positive"
    if row["exact_common_area_mm2"] < policy["min_overlap_area_mm2"]:
        return "overlap_area_below_threshold"
    if min(row["exact_coverage_a"], row["exact_coverage_b"]) < policy["min_face_coverage"]:
        return "coverage_below_threshold"
    if row["effective_width_mm"] < policy["min_effective_width_mm"]:
        return "effective_width_below_threshold"
    if row["score"] < policy["min_score"]:
        return "score_below_threshold"
    if row["same_part_relation"] == "same_part":
        topology = row["topology_class"]
        if topology == "topology_unknown":
            return "topology_unknown_rejected"
        if policy["same_part_topology"] == "exclude_shared_edge" and topology == "shared_edge":
            return "shared_edge_excluded"
        if policy["same_part_topology"] == "disjoint_boundaries_only" and topology != "disjoint_boundaries":
            return "topology_not_disjoint_boundaries"
    return None


def replay_controlled_pair_policies(audit: dict[str, Any]) -> dict[str, Any]:
    """Replay the fixed policy matrix using only a previously measured audit.

    This function has no truth, reference, identity, or label input.  It is
    intentionally suitable for deterministic policy generation only; offline
    evaluation augments its output in the command layer.
    """

    if audit.get("scope") != "offline_controlled_pair_geometry_audit" or not isinstance(audit.get("pairs"), list):
        raise ValueError("invalid controlled pair geometry audit")
    cases: list[dict[str, Any]] = []
    for policy in _controlled_policy_cases():
        accepted: list[dict[str, Any]] = []
        rejected: dict[str, int] = {}
        for row in audit["pairs"]:
            reason = _replay_pair(row, policy)
            if reason is None:
                accepted.append(row)
            else:
                rejected[reason] = rejected.get(reason, 0) + 1
        selected = sorted({endpoint for row in accepted for endpoint in (row["face_a_id"], row["face_b_id"])})
        cases.append({
            "parameters": policy,
            "selected_face_ids": selected,
            "supporting_pairs": [row["pair_id"] for row in accepted],
            "accepted_same_part_count": sum(row["same_part_relation"] == "same_part" for row in accepted),
            "accepted_cross_part_count": sum(row["same_part_relation"] == "different_parts" for row in accepted),
            "rejection_attribution": dict(sorted(rejected.items())),
        })
    return {"format_version": 1, "scope": "offline_controlled_pair_policy_replay", "production_behavior_changed": False, "case_count": len(cases), "cases": cases}


def evaluate_controlled_pair_policy_replay(replay: dict[str, Any], offline_truth_face_ids: Iterable[str]) -> dict[str, Any]:
    """Append explicit offline-only metrics without feeding them into replay."""

    truth = set(offline_truth_face_ids)
    evaluated: list[dict[str, Any]] = []
    for case in replay["cases"]:
        selected = set(case["selected_face_ids"])
        tp, fp, fn = len(selected & truth), len(selected - truth), len(truth - selected)
        metrics = {
            "true_positives": tp, "false_positives": fp, "false_negatives": fn,
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "recall": tp / (tp + fn) if tp + fn else 0.0,
            "passed": (tp / (tp + fp) > 0.9 if tp + fp else False) and (tp / (tp + fn) > 0.9 if tp + fn else False),
        }
        evaluated.append({**case, **metrics, "evaluation_only": metrics})
    topology_strength = {"no_constraint": 0, "exclude_shared_edge": 1, "disjoint_boundaries_only": 2}
    strict = [case for case in evaluated if case["passed"]]
    strict.sort(key=lambda case: (
        -case["recall"], -case["precision"], case["false_positives"], case["false_negatives"],
        -case["parameters"]["min_overlap_area_mm2"], -case["parameters"]["min_face_coverage"],
        -case["parameters"]["min_effective_width_mm"], -case["parameters"]["min_score"],
        -topology_strength[case["parameters"]["same_part_topology"]],
        tuple(case["parameters"].items()),
    ))
    return {"format_version": 1, "scope": "offline_controlled_pair_policy_search", "production_behavior_changed": False, "evaluation_inputs": "explicit offline truth; not used by geometry audit or policy replay", "quality_gate": {"minimum_precision_exclusive": 0.9, "minimum_recall_exclusive": 0.9}, "case_count": len(evaluated), "selected_strict_pass_policy": strict[0] if strict else None, "cases": evaluated}
