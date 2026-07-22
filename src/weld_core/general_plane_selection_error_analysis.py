"""Join and validate offline generic-plane-selection error-analysis inputs.

This module is deliberately offline-only.  It consumes an evaluation result
and the two selection audit artifacts; it must never be imported by the
runtime selector or pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ErrorAnalysisInputError(ValueError):
    """Raised when evaluation and audit artifacts cannot be joined safely."""


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
