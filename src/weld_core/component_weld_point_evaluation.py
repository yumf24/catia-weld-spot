"""Explicit offline evaluation and error reporting for component weld points.

Candidate generation lives in :mod:`component_weld_evaluation` and never
imports this module.  This module is evaluation-only: it joins a completed
candidate document with the separately extracted SPOT marker centers.
"""

from __future__ import annotations

from statistics import median
from typing import Any

from .evaluate import evaluate
from .schema import CandidatesDocument, GroundTruthDocument


PRIMARY_TOLERANCE_MM = 10.0
SENSITIVITY_TOLERANCES_MM = (5.0, 10.0, 20.0)


def _summary(document: Any) -> dict[str, float | int]:
    summary = document.summary
    precision = summary.precision
    recall = summary.recall
    distances = [match.distance_mm for match in document.matches]
    return {
        "ground_truth_count": summary.num_ground_truth,
        "candidate_count": summary.num_candidates,
        "true_positives": summary.true_positives,
        "false_positives": summary.false_positives,
        "false_negatives": summary.false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": (2 * precision * recall / (precision + recall)) if precision + recall else 0.0,
        "mean_error_mm": summary.mean_error_mm,
        "median_error_mm": float(median(distances)) if distances else 0.0,
        "max_error_mm": summary.max_error_mm,
    }


def _assert_counts(summary: dict[str, float | int], errors: dict[str, list[dict[str, Any]]]) -> None:
    expected = {
        "true_positives": len(errors["true_positives"]),
        "false_positives": len(errors["false_positives"]),
        "false_negatives": len(errors["false_negatives"]),
    }
    for field, count in expected.items():
        if summary[field] != count:
            raise ValueError(f"{field}={summary[field]} does not equal point-level count {count}")


def _stratify_candidates(candidates: CandidatesDocument) -> dict[str, dict[str, int]]:
    """Publish candidate counts by audit-relevant geometry properties."""
    result: dict[str, dict[str, int]] = {"confidence_tier": {}, "layer_count": {}, "interface_count": {}}
    for candidate in candidates.candidates:
        for field, value in (
            ("confidence_tier", candidate.confidence_tier),
            ("layer_count", str(candidate.layer_count)),
            ("interface_count", str(len(candidate.supporting_interfaces))),
        ):
            result[field][value] = result[field].get(value, 0) + 1
    return result


def enrich_with_planar_adjudication(
    report: dict[str, Any], analysis: dict[str, Any], adjudication: dict[str, Any], candidates: CandidatesDocument,
    candidate_audit: dict[str, Any] | None = None,
) -> None:
    """Add the independent planar-supported denominator and conservative FN causes.

    This is deliberately evaluation-only.  It never feeds any selection or
    layout decision back into production candidates.
    """
    rows = {row["ground_truth_id"]: row for row in adjudication["points"]}
    supported_ids = {key for key, row in rows.items() if row["status"] == "planar_supported"}
    truth_positions = {row["ground_truth_id"]: row["position_mm"] for row in rows.values()}
    matched_ids = {row["ground_truth_id"] for row in analysis["true_positives"]}
    supported_tp = len(supported_ids & matched_ids)
    supported_fn = len(supported_ids - matched_ids)
    candidate_count = len(candidates.candidates)
    report["planar_supported_summary"] = {
        "ground_truth_count": len(supported_ids),
        "true_positives": supported_tp,
        "false_negatives": supported_fn,
        "recall": supported_tp / len(supported_ids) if supported_ids else 0.0,
        "candidate_count": candidate_count,
    }
    report["candidate_stratification"] = _stratify_candidates(candidates)
    audit_points = (candidate_audit or {}).get("original_exact_layout_points", [])
    audit_interfaces = {interface for point in audit_points for interface in point.get("source_interfaces", [])}
    excluded_points = [
        point for point in (candidate_audit or {}).get("final_candidates", [])
        if point.get("status") == "budget_excluded"
    ]
    merged_points = [
        point for point in (candidate_audit or {}).get("merges", [])
        if point.get("status") in {"merged", "filtered"}
    ]

    def distance(position: list[float] | tuple[float, float, float], other: list[float] | tuple[float, float, float]) -> float:
        return sum((a - b) ** 2 for a, b in zip(position, other)) ** 0.5

    for row in analysis["false_negatives"]:
        adjudication_row = rows.get(row["ground_truth_id"])
        if adjudication_row is None or adjudication_row["status"] != "planar_supported":
            row["attribution"] = "out_of_scope_or_unresolved"
            continue
        position = truth_positions[row["ground_truth_id"]]
        interfaces = set(adjudication_row.get("supporting_interfaces", []))
        if candidate_audit is not None and interfaces and not interfaces & audit_interfaces:
            row["attribution"] = "interface_not_found"
            continue
        if any(distance(position, point.get("position_mm", [])) <= PRIMARY_TOLERANCE_MM for point in excluded_points):
            row["attribution"] = "budget_excluded"
            continue
        if any(distance(position, point.get("position_mm", [])) <= PRIMARY_TOLERANCE_MM for point in merged_points):
            row["attribution"] = "merged_or_filtered"
            continue
        nearest = min((distance(position, candidate.position) for candidate in candidates.candidates), default=float("inf"))
        # A supported point with no candidate within a coverage radius is a
        # region/layout issue; inside that radius but outside 10 mm is a layout
        # offset.  Categories are selected only from offline audit evidence.
        row["attribution"] = "layout_offset" if nearest <= 20.0 else "region_not_covered"
    analysis["false_negative_attribution_counts"] = {
        reason: sum(row.get("attribution") == reason for row in analysis["false_negatives"])
        for reason in ("out_of_scope_or_unresolved", "interface_not_found", "region_not_covered", "layout_offset", "merged_or_filtered", "budget_excluded")
    }


def evaluate_component_weld_points(
    ground_truth: GroundTruthDocument, candidates: CandidatesDocument
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the primary report and traceable point-level error analysis."""
    primary = evaluate(ground_truth, candidates, tolerance_mm=PRIMARY_TOLERANCE_MM)
    truth_by_id = {point.id: point for point in ground_truth.points}
    candidate_by_id = {candidate.id: candidate for candidate in candidates.candidates}

    def candidate_trace(candidate_id: str) -> dict[str, Any]:
        candidate = candidate_by_id[candidate_id]
        return {
            "candidate_faces": candidate.faces,
            "candidate_layer_count": candidate.layer_count,
            "candidate_supporting_interfaces": candidate.supporting_interfaces,
            "candidate_confidence_tier": candidate.confidence_tier,
            "candidate_exact_region_refs": candidate.exact_region_refs,
        }

    errors: dict[str, list[dict[str, Any]]] = {
        "true_positives": [
            {
                "ground_truth_id": match.ground_truth_id,
                "ground_truth_position_mm": truth_by_id[match.ground_truth_id].position,
                "candidate_id": match.candidate_id,
                "candidate_position_mm": candidate_by_id[match.candidate_id].position,
                "distance_mm": match.distance_mm,
                **candidate_trace(match.candidate_id),
            }
            for match in primary.matches
        ],
        "false_negatives": [
            {
                "ground_truth_id": point_id,
                "ground_truth_position_mm": truth_by_id[point_id].position,
                "ground_truth_label": truth_by_id[point_id].label,
            }
            for point_id in primary.unmatched_ground_truth
        ],
        "false_positives": [
            {
                "candidate_id": candidate_id,
                "candidate_position_mm": candidate_by_id[candidate_id].position,
                **candidate_trace(candidate_id),
            }
            for candidate_id in primary.unmatched_candidates
        ],
    }
    summary = _summary(primary)
    _assert_counts(summary, errors)
    sensitivity = {
        str(tolerance): _summary(evaluate(ground_truth, candidates, tolerance_mm=tolerance))
        for tolerance in SENSITIVITY_TOLERANCES_MM
    }
    report = {
        "format_version": 1,
        "scope": "offline_component_weld_point_evaluation",
        "evaluation_only": True,
        "matching": "greedy_nearest_distance_one_to_one",
        "primary_tolerance_mm": PRIMARY_TOLERANCE_MM,
        "summary": summary,
        "candidate_stratification": _stratify_candidates(candidates),
        "sensitivity_by_tolerance_mm": sensitivity,
    }
    analysis = {
        "format_version": 1,
        "scope": "offline_component_weld_point_error_analysis",
        "evaluation_only": True,
        "primary_tolerance_mm": PRIMARY_TOLERANCE_MM,
        "summary": summary,
        **errors,
    }
    return report, analysis


def evaluation_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Component weld point evaluation",
        "",
        "Offline single-dataset evidence only; this report does not alter candidate generation.",
        "",
        f"Primary tolerance: {report['primary_tolerance_mm']} mm (greedy nearest-distance one-to-one)",
        "",
        "| TP | FP | FN | Precision | Recall | F1 | Mean error (mm) | Median error (mm) | Max error (mm) |",
        "| -: | -: | -: | -: | -: | -: | -: | -: | -: |",
        f"| {summary['true_positives']} | {summary['false_positives']} | {summary['false_negatives']} | {summary['precision']:.4f} | {summary['recall']:.4f} | {summary['f1']:.4f} | {summary['mean_error_mm']:.4f} | {summary['median_error_mm']:.4f} | {summary['max_error_mm']:.4f} |",
        "",
        "## Sensitivity",
        "",
        "| Tolerance (mm) | TP | FP | FN | Precision | Recall | F1 |",
        "| -: | -: | -: | -: | -: | -: | -: |",
    ]
    for tolerance, row in report["sensitivity_by_tolerance_mm"].items():
        lines.append(f"| {tolerance} | {row['true_positives']} | {row['false_positives']} | {row['false_negatives']} | {row['precision']:.4f} | {row['recall']:.4f} | {row['f1']:.4f} |")
    return "\n".join(lines) + "\n"


def error_analysis_markdown(analysis: dict[str, Any]) -> str:
    summary = analysis["summary"]
    return "\n".join([
        "# Component weld point error analysis",
        "",
        "Offline evaluation-only point classifications. Candidate face IDs are retained for manual review.",
        "",
        f"TP: {summary['true_positives']}  ",
        f"FP: {summary['false_positives']}  ",
        f"FN: {summary['false_negatives']}  ",
        "",
        f"The companion JSON contains {len(analysis['true_positives'])} TP coordinates/distances/faces, {len(analysis['false_positives'])} FP coordinates/faces, and {len(analysis['false_negatives'])} FN coordinates.",
        "",
    ])
