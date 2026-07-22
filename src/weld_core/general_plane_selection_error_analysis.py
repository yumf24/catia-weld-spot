"""Join and validate offline generic-plane-selection error-analysis inputs.

This module is deliberately offline-only.  It consumes an evaluation result
and the two selection audit artifacts; it must never be imported by the
runtime selector or pipeline.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from itertools import product
from pathlib import Path
from typing import Any, Callable

from .general_plane_selection import GeneralPairAudit, GeneralPlaneFace, GeneralSelectionParams, select_general_planar_faces
from .general_plane_selection_evaluation import evaluate_general_plane_selection


_REPORT_RECOMMENDATIONS = {
    "plane_gap": "Investigate a larger or layered plane-gap strategy before changing production defaults.",
    "projected_aabb": "Diagnose whether projected-AABB rejection reflects true non-overlap or a pre-filter limitation.",
    "same_part_policy": "Evaluate same-part pairs separately, with precision impact measured offline.",
}

_SWEEP_MAX_PLANE_GAP_MM = (0.2, 0.3, 0.5, 0.8, 1.0, 1.5, 3.0)
_SWEEP_ALLOW_SAME_PART_PAIRS = (False, True)
_SWEEP_MIN_FACE_COVERAGE = (0.02, 0.05)


class ErrorAnalysisInputError(ValueError):
    """Raised when evaluation and audit artifacts cannot be joined safely."""


def controlled_parameter_sweep_cases() -> list[GeneralSelectionParams]:
    """Return the fixed 7 x 2 x 2 offline diagnostic sweep matrix.

    All thresholds not explicitly varied retain their production defaults.  The
    returned parameter objects are used only by the offline analysis command;
    this function never mutates a runtime default.
    """

    return [
        GeneralSelectionParams(
            max_plane_gap_mm=max_plane_gap_mm,
            allow_same_part_pairs=allow_same_part_pairs,
            min_face_coverage=min_face_coverage,
        )
        for max_plane_gap_mm, allow_same_part_pairs, min_face_coverage in product(
            _SWEEP_MAX_PLANE_GAP_MM,
            _SWEEP_ALLOW_SAME_PART_PAIRS,
            _SWEEP_MIN_FACE_COVERAGE,
        )
    ]


def build_controlled_parameter_sweep(
    evaluate_case: Callable[[GeneralSelectionParams], dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate every fixed sweep case and return a portable offline report.

    ``evaluate_case`` makes the matrix and report contract unit-testable
    without requiring CAD geometry.  It must return an evaluation result with
    a ``summary`` object, as produced by ``evaluate_general_plane_selection``.
    """

    rows: list[dict[str, Any]] = []
    summary_fields = (
        "predicted_faces",
        "truth_faces",
        "true_positives",
        "false_positives",
        "false_negatives",
        "precision",
        "recall",
        "passed",
    )
    for params in controlled_parameter_sweep_cases():
        result = evaluate_case(params)
        summary = result.get("summary") if isinstance(result, dict) else None
        if not isinstance(summary, dict) or any(field not in summary for field in summary_fields):
            raise ErrorAnalysisInputError("parameter sweep case returned no complete evaluation summary")
        rows.append({"parameters": asdict(params), "summary": {field: summary[field] for field in summary_fields}})
    return {
        "format_version": 1,
        "scope": "offline_evaluation_only",
        "matrix": {
            "max_plane_gap_mm": list(_SWEEP_MAX_PLANE_GAP_MM),
            "allow_same_part_pairs": list(_SWEEP_ALLOW_SAME_PART_PAIRS),
            "min_face_coverage": list(_SWEEP_MIN_FACE_COVERAGE),
        },
        "case_count": len(rows),
        "cases": rows,
    }


def run_controlled_parameter_sweep(
    source_faces: list[GeneralPlaneFace], reference_faces: list[GeneralPlaneFace]
) -> dict[str, Any]:
    """Run the fixed selection sweep against explicit offline reference faces.

    Exact CAD overlap is invariant across this matrix.  It is therefore
    measured once using the most permissive matrix row and the resulting audit
    is replayed for every row.  This avoids 28 identical OCP boolean passes
    while retaining each row's original decision order and thresholds.
    """

    base_selection = select_general_planar_faces(
        source_faces,
        GeneralSelectionParams(max_plane_gap_mm=max(_SWEEP_MAX_PLANE_GAP_MM), allow_same_part_pairs=True, min_face_coverage=min(_SWEEP_MIN_FACE_COVERAGE)),
    )

    def evaluate_case(params: GeneralSelectionParams) -> dict[str, Any]:
        selected_ids = _selected_ids_from_sweep_audit(base_selection.pair_audits, params)
        return evaluate_general_plane_selection(source_faces, reference_faces, selected_ids)

    return build_controlled_parameter_sweep(evaluate_case)


def _selected_ids_from_sweep_audit(
    audits: tuple[GeneralPairAudit, ...], params: GeneralSelectionParams
) -> tuple[str, ...]:
    """Replay threshold decisions from the single permissive sweep audit."""

    selected: set[str] = set()
    for audit in audits:
        if audit.part_a == audit.part_b and not params.allow_same_part_pairs:
            continue
        if audit.normal_angle_deg is None or audit.normal_angle_deg > params.max_normal_angle_deg:
            continue
        if audit.plane_gap_mm is None or audit.plane_gap_mm > params.max_plane_gap_mm:
            continue
        if audit.aabb_overlap_width_mm is None or audit.aabb_overlap_height_mm is None:
            continue
        if min(audit.aabb_overlap_width_mm, audit.aabb_overlap_height_mm) < params.min_effective_width_mm:
            continue
        if audit.common_area_mm2 < params.min_overlap_area_mm2:
            continue
        if min(audit.coverage_a, audit.coverage_b) < params.min_face_coverage:
            continue
        selected.update((audit.face_a_id, audit.face_b_id))
    return tuple(sorted(selected))


def render_controlled_parameter_sweep_markdown(report: dict[str, Any]) -> str:
    """Render a compact comparison table for the controlled sweep."""

    cases = report.get("cases")
    if report.get("scope") != "offline_evaluation_only" or not isinstance(cases, list):
        raise ErrorAnalysisInputError("invalid controlled parameter sweep report")
    lines = [
        "# General plane selection parameter sweep",
        "",
        "Scope: offline evaluation only. This diagnostic does not change production selection parameters.",
        "",
        "| Gap (mm) | Same-part pairs | Min coverage | TP | FP | FN | Precision | Recall |",
        "| ---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case in cases:
        params, summary = case["parameters"], case["summary"]
        lines.append(
            "| {gap:g} | {same_part} | {coverage:g} | {tp} | {fp} | {fn} | {precision:.2%} | {recall:.2%} |".format(
                gap=params["max_plane_gap_mm"],
                same_part="true" if params["allow_same_part_pairs"] else "false",
                coverage=params["min_face_coverage"],
                tp=summary["true_positives"], fp=summary["false_positives"], fn=summary["false_negatives"],
                precision=summary["precision"], recall=summary["recall"],
            )
        )
    return "\n".join(lines) + "\n"


_FN_REASON_DETAILS = {
    "overlap_area_below_threshold": (
        "overlap_area",
        "investigate_overlap_area_threshold",
        0,
    ),
    "coverage_below_threshold": (
        "coverage",
        "investigate_face_coverage_threshold",
        1,
    ),
    "projected_aabb_no_overlap": (
        "projected_aabb",
        "diagnose_projected_aabb_pre_filter",
        2,
    ),
    "plane_gap_exceeds_threshold": (
        "plane_gap",
        "investigate_gap_threshold_or_layered_gap_strategy",
        3,
    ),
    "same_part_excluded": (
        "same_part_policy",
        "evaluate_same_part_pair_policy",
        4,
    ),
    "normal_angle_exceeds_threshold": (
        "normal_angle",
        "investigate_normal_angle_threshold",
        5,
    ),
}


def _load_json(path: str | Path, label: str) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ErrorAnalysisInputError(f"cannot read {label}: {source}") from exc
    if not isinstance(value, dict):
        raise ErrorAnalysisInputError(f"{label} must contain a JSON object")
    return value


def _face_ids(rows: Any, label: str) -> list[str]:
    if not isinstance(rows, list):
        raise ErrorAnalysisInputError(f"{label} must be a list")
    face_ids: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("face_id"), str):
            raise ErrorAnalysisInputError(f"{label}[{index}] must contain string face_id")
        face_ids.append(row["face_id"])
    if len(face_ids) != len(set(face_ids)):
        raise ErrorAnalysisInputError(f"{label} contains duplicate face_id values")
    return face_ids


def _require_summary_counts(evaluation: dict[str, Any], tp: set[str], fp: set[str], fn: set[str]) -> None:
    summary = evaluation.get("summary")
    if not isinstance(summary, dict):
        raise ErrorAnalysisInputError("evaluation.summary must be an object")
    expected = {
        "true_positives": len(tp),
        "false_positives": len(fp),
        "false_negatives": len(fn),
    }
    for field, value in expected.items():
        if summary.get(field) != value:
            raise ErrorAnalysisInputError(
                f"evaluation.summary.{field}={summary.get(field)!r} does not match face rows ({value})"
            )


def join_error_analysis(
    evaluation: dict[str, Any],
    pair_audit: dict[str, Any],
    selection_audit: dict[str, Any],
) -> dict[str, Any]:
    """Return a validated face-level join of offline evaluation and audits."""

    tp = set(_face_ids(evaluation.get("true_positive_faces"), "evaluation.true_positive_faces"))
    fp = set(_face_ids(evaluation.get("false_positive_faces"), "evaluation.false_positive_faces"))
    fn = set(_face_ids(evaluation.get("false_negative_faces"), "evaluation.false_negative_faces"))
    if tp & fp or tp & fn or fp & fn:
        raise ErrorAnalysisInputError("evaluation TP, FP, and FN face sets must be disjoint")
    _require_summary_counts(evaluation, tp, fp, fn)

    selected_rows = selection_audit.get("selected_faces")
    rejected_rows = selection_audit.get("rejected_faces")
    selected_ids = set(_face_ids(selected_rows, "selection_audit.selected_faces"))
    rejected_ids = set(_face_ids(rejected_rows, "selection_audit.rejected_faces"))
    if selected_ids & rejected_ids:
        raise ErrorAnalysisInputError("selection audit has faces in both selected and rejected sets")
    if selection_audit.get("selected_face_count") != len(selected_ids):
        raise ErrorAnalysisInputError("selection_audit.selected_face_count does not match selected_faces")
    source_ids = selected_ids | rejected_ids
    if selection_audit.get("total_planar_faces") != len(source_ids):
        raise ErrorAnalysisInputError("selection_audit.total_planar_faces does not match audited face sets")

    pair_rows = pair_audit.get("pairs")
    if not isinstance(pair_rows, list):
        raise ErrorAnalysisInputError("pair_audit.pairs must be a list")
    pairs_by_id: dict[str, dict[str, Any]] = {}
    for index, pair in enumerate(pair_rows):
        if not isinstance(pair, dict):
            raise ErrorAnalysisInputError(f"pair_audit.pairs[{index}] must be an object")
        pair_id = pair.get("id")
        endpoints = (pair.get("face_a_id"), pair.get("face_b_id"))
        if not isinstance(pair_id, str) or not all(isinstance(face_id, str) for face_id in endpoints):
            raise ErrorAnalysisInputError(f"pair_audit.pairs[{index}] has invalid id or face endpoints")
        if pair_id in pairs_by_id:
            raise ErrorAnalysisInputError(f"pair_audit contains duplicate pair id {pair_id!r}")
        if not set(endpoints) <= source_ids:
            raise ErrorAnalysisInputError(f"pair {pair_id!r} references a face missing from selection audit")
        pairs_by_id[pair_id] = pair

    support_by_face: dict[str, list[dict[str, Any]]] = {}
    for row in selected_rows:
        face_id = row["face_id"]
        support_ids = row.get("supporting_pair_ids")
        if not isinstance(support_ids, list) or not support_ids or not all(isinstance(value, str) for value in support_ids):
            raise ErrorAnalysisInputError(f"selected face {face_id!r} must have supporting_pair_ids")
        support: list[dict[str, Any]] = []
        for pair_id in support_ids:
            pair = pairs_by_id.get(pair_id)
            if pair is None:
                raise ErrorAnalysisInputError(f"selected face {face_id!r} references missing pair {pair_id!r}")
            if not pair.get("accepted") or face_id not in {pair["face_a_id"], pair["face_b_id"]}:
                raise ErrorAnalysisInputError(f"selected face {face_id!r} has invalid supporting pair {pair_id!r}")
            support.append(pair)
        support_by_face[face_id] = support

    predicted_ids = tp | fp
    if predicted_ids != selected_ids:
        missing = sorted(predicted_ids - selected_ids)
        extra = sorted(selected_ids - predicted_ids)
        raise ErrorAnalysisInputError(
            f"evaluation predictions and selection audit differ (missing selected={missing}, extra selected={extra})"
        )
    truth_ids = tp | fn
    if not truth_ids <= source_ids:
        raise ErrorAnalysisInputError(f"offline truth references unknown source faces: {sorted(truth_ids - source_ids)}")

    faces: list[dict[str, Any]] = []
    for face_id in sorted(source_ids | predicted_ids | truth_ids):
        classification = "true_positive" if face_id in tp else "false_positive" if face_id in fp else "false_negative" if face_id in fn else "unclassified"
        faces.append(
            {
                "face_id": face_id,
                "classification": classification,
                "is_truth_face": face_id in truth_ids,
                "is_predicted": face_id in predicted_ids,
                "selection_status": "selected" if face_id in selected_ids else "rejected",
                "supporting_pairs": support_by_face.get(face_id, []),
            }
        )
    return {
        "format_version": 1,
        "summary": evaluation["summary"],
        "parameters": selection_audit.get("parameters"),
        "faces": faces,
    }


def _counterpart(pair: dict[str, Any], face_id: str) -> tuple[str, str | None]:
    """Return the opposite face and its part after the join has validated endpoints."""

    if pair["face_a_id"] == face_id:
        return pair["face_b_id"], pair.get("part_b")
    if pair["face_b_id"] == face_id:
        return pair["face_a_id"], pair.get("part_a")
    raise ErrorAnalysisInputError(f"pair {pair['id']!r} does not contain false-negative face {face_id!r}")


def _fn_pair_sort_key(pair: dict[str, Any]) -> tuple[int, str]:
    """Prefer failures that reached the deepest geometry-validation stage.

    A pair rejected after precise overlap or coverage measurement is stronger
    diagnostic evidence than an early rejection.  Among early rejections, a
    passed-gap AABB failure is more useful than a gap failure; same-part is
    retained ahead of normal-angle-only evidence because it represents a
    separately controllable policy.  Pair IDs make ties reproducible.
    """

    details = _FN_REASON_DETAILS.get(pair.get("reason"))
    return (details[2] if details is not None else 6, pair["id"])


def classify_false_negatives(joined: dict[str, Any], pair_audit: dict[str, Any]) -> list[dict[str, Any]]:
    """Classify each false negative using its most diagnostic failed pair.

    ``joined`` must be the result of :func:`join_error_analysis`; ``pair_audit``
    is retained separately so analysis can inspect all rejected pairs without
    changing the compact face-level join contract.
    """

    pair_rows = pair_audit.get("pairs")
    if not isinstance(pair_rows, list):
        raise ErrorAnalysisInputError("pair_audit.pairs must be a list")
    pairs_by_face: dict[str, list[dict[str, Any]]] = {}
    for pair in pair_rows:
        if not isinstance(pair, dict) or not isinstance(pair.get("id"), str):
            raise ErrorAnalysisInputError("pair_audit.pairs must contain objects with string ids")
        for endpoint in (pair.get("face_a_id"), pair.get("face_b_id")):
            if isinstance(endpoint, str):
                pairs_by_face.setdefault(endpoint, []).append(pair)

    classifications: list[dict[str, Any]] = []
    for face in joined.get("faces", []):
        if face.get("classification") != "false_negative":
            continue
        face_id = face.get("face_id")
        if not isinstance(face_id, str):
            raise ErrorAnalysisInputError("joined false-negative face must contain string face_id")
        failed_pairs = [pair for pair in pairs_by_face.get(face_id, []) if not pair.get("accepted")]
        if not failed_pairs:
            classifications.append(
                {
                    "face_id": face_id,
                    "failure_stage": "no_evidence",
                    "recommended_recovery": "review_pair_audit_coverage",
                    "best_failed_pair": None,
                }
            )
            continue

        pair = min(failed_pairs, key=_fn_pair_sort_key)
        counterpart_face_id, counterpart_part = _counterpart(pair, face_id)
        failure_stage, recommended_recovery, _ = _FN_REASON_DETAILS.get(
            pair.get("reason"),
            ("no_evidence", "review_unrecognized_pair_rejection", 6),
        )
        classifications.append(
            {
                "face_id": face_id,
                "failure_stage": failure_stage,
                "recommended_recovery": recommended_recovery,
                "best_failed_pair": {
                    "pair_id": pair["id"],
                    "reason": pair.get("reason"),
                    "counterpart_face_id": counterpart_face_id,
                    "parts": {
                        "source_part": pair.get("part_a") if pair["face_a_id"] == face_id else pair.get("part_b"),
                        "counterpart_part": counterpart_part,
                        "relation": "same_part" if pair.get("part_a") == pair.get("part_b") else "different_parts",
                    },
                    "normal_angle_deg": pair.get("normal_angle_deg"),
                    "plane_gap_mm": pair.get("plane_gap_mm"),
                    "aabb_overlap_width_mm": pair.get("aabb_overlap_width_mm"),
                    "aabb_overlap_height_mm": pair.get("aabb_overlap_height_mm"),
                    "common_area_mm2": pair.get("common_area_mm2"),
                    "coverage_a": pair.get("coverage_a"),
                    "coverage_b": pair.get("coverage_b"),
                },
            }
        )
    return classifications


def classify_false_positives(joined: dict[str, Any]) -> list[dict[str, Any]]:
    """Explain selected faces absent from the offline truth mapping.

    The validated join has already ensured that every supporting pair is
    accepted and contains its selected face.  This function retains every
    support (rather than choosing one) because multiple supports are evidence
    for a false positive's selection.
    """

    truth_face_ids = {
        face["face_id"]
        for face in joined.get("faces", [])
        if isinstance(face, dict) and face.get("is_truth_face") and isinstance(face.get("face_id"), str)
    }
    classifications: list[dict[str, Any]] = []
    for face in joined.get("faces", []):
        if not isinstance(face, dict) or face.get("classification") != "false_positive":
            continue
        face_id = face.get("face_id")
        supporting_pairs = face.get("supporting_pairs")
        if not isinstance(face_id, str) or not isinstance(supporting_pairs, list) or not supporting_pairs:
            raise ErrorAnalysisInputError("joined false-positive face must have a face_id and supporting pairs")
        supports: list[dict[str, Any]] = []
        for pair in supporting_pairs:
            if not isinstance(pair, dict) or not pair.get("accepted"):
                raise ErrorAnalysisInputError(f"false-positive face {face_id!r} has invalid supporting pair")
            counterpart_face_id, counterpart_part = _counterpart(pair, face_id)
            supports.append(
                {
                    "pair_id": pair["id"],
                    "counterpart_face_id": counterpart_face_id,
                    "counterpart_part": counterpart_part,
                    "counterpart_is_truth_face": counterpart_face_id in truth_face_ids,
                    "common_area_mm2": pair.get("common_area_mm2"),
                    "coverage_a": pair.get("coverage_a"),
                    "coverage_b": pair.get("coverage_b"),
                    "score": pair.get("score"),
                }
            )
        has_truth_support = any(support["counterpart_is_truth_face"] for support in supports)
        classifications.append(
            {
                "face_id": face_id,
                "is_unknown_predicted_face": True,
                "false_positive_reason": (
                    "accepted_pair_connects_offline_truth" if has_truth_support else "accepted_pair_not_in_offline_truth"
                ),
                "supporting_pairs": supports,
            }
        )
    return classifications


def build_error_analysis_report(joined: dict[str, Any], pair_audit: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic, human-reviewable offline error-analysis report."""

    false_negatives = classify_false_negatives(joined, pair_audit)
    false_positives = classify_false_positives(joined)
    fn_reason_counts: dict[str, int] = {}
    for item in false_negatives:
        stage = item["failure_stage"]
        fn_reason_counts[stage] = fn_reason_counts.get(stage, 0) + 1
    ranked_fn_reasons = [
        {
            "failure_stage": stage,
            "count": count,
            "recommended_direction": _REPORT_RECOMMENDATIONS.get(
                stage, "Review the supporting audit evidence before changing selection behavior."
            ),
        }
        for stage, count in sorted(fn_reason_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "format_version": 1,
        "scope": "offline_evaluation_only",
        "summary": joined["summary"],
        "false_negative_reason_ranking": ranked_fn_reasons,
        "optimization_priority": [
            "plane_gap_strategy",
            "projected_aabb_diagnosis",
            "same_part_pair_policy_evaluation",
        ],
        "false_negatives": false_negatives,
        "false_positives": false_positives,
    }


def render_error_analysis_markdown(report: dict[str, Any]) -> str:
    """Render the compact Markdown companion for an error-analysis report."""

    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise ErrorAnalysisInputError("error-analysis report summary must be an object")
    true_positives = summary.get("true_positives")
    false_positives = summary.get("false_positives")
    false_negatives = summary.get("false_negatives")
    if not all(isinstance(value, int) and value >= 0 for value in (true_positives, false_positives, false_negatives)):
        raise ErrorAnalysisInputError("error-analysis report summary must contain non-negative TP/FP/FN counts")
    precision = summary.get("precision")
    recall = summary.get("recall")
    if not isinstance(precision, (int, float)):
        precision = true_positives / (true_positives + false_positives) if true_positives + false_positives else 0.0
    if not isinstance(recall, (int, float)):
        recall = true_positives / (true_positives + false_negatives) if true_positives + false_negatives else 0.0
    lines = [
        "# General plane selection error analysis",
        "",
        "Scope: offline evaluation only. This report does not change production selection parameters.",
        "",
        "## Face-level baseline",
        "",
        "| TP | FP | FN | Precision | Recall |",
        "| ---: | ---: | ---: | ---: | ---: |",
        f"| {true_positives} | {false_positives} | {false_negatives} | {precision:.2%} | {recall:.2%} |",
        "",
        "## False-negative root causes",
        "",
        "| Rank | Failure stage | Faces | Recommended direction |",
        "| ---: | --- | ---: | --- |",
    ]
    for rank, item in enumerate(report.get("false_negative_reason_ranking", []), start=1):
        lines.append(
            f"| {rank} | {item['failure_stage']} | {item['count']} | {item['recommended_direction']} |"
        )
    lines.extend(["", "## Recommended optimization order", ""])
    for rank, item in enumerate(report.get("optimization_priority", []), start=1):
        lines.append(f"{rank}. `{item}`")
    lines.extend(["", "## False positives", ""])
    for item in report.get("false_positives", []):
        lines.append(
            f"- `{item['face_id']}`: {item['false_positive_reason']} "
            f"({len(item['supporting_pairs'])} accepted supporting pair(s))."
        )
    return "\n".join(lines) + "\n"


def load_and_join_error_analysis(
    evaluation_path: str | Path,
    pair_audit_path: str | Path,
    selection_audit_path: str | Path,
) -> dict[str, Any]:
    """Load three artifact files and return their validated join."""

    return join_error_analysis(
        _load_json(evaluation_path, "evaluation"),
        _load_json(pair_audit_path, "pair audit"),
        _load_json(selection_audit_path, "selection audit"),
    )
