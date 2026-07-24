"""Evaluation-only Recall--Precision operating-frontier reporting.

Nothing in this module is imported by candidate selection, region layout, or
CATIA write-back.  It consumes an already-completed candidate ordering plus
truth and planar adjudication that are explicitly evaluation-only inputs.
"""

from __future__ import annotations

from math import ceil
from statistics import median
from typing import Any, Iterable

from .evaluate import evaluate
from .schema import Candidate, CandidatesDocument, GroundTruthDocument


PRIMARY_TOLERANCE_MM = 10.0
PLANAR_SUPPORTED_RECALL_TARGET = 0.80


class OperatingFrontierError(ValueError):
    """Raised when an evaluation frontier cannot be traced unambiguously."""


def _unique_ids(values: Iterable[str], label: str) -> set[str]:
    result: set[str] = set()
    for value in values:
        if value in result:
            raise OperatingFrontierError(f"duplicate {label} id: {value!r}")
        result.add(value)
    return result


def _distance_summary(values: list[float]) -> dict[str, float]:
    return {
        "mean_error_mm": sum(values) / len(values) if values else 0.0,
        "median_error_mm": float(median(values)) if values else 0.0,
        "max_error_mm": max(values) if values else 0.0,
    }


def _full_summary(document: Any) -> dict[str, float | int]:
    summary = document.summary
    distances = [match.distance_mm for match in document.matches]
    return {
        "ground_truth_count": summary.num_ground_truth,
        "candidate_count": summary.num_candidates,
        "true_positives": summary.true_positives,
        "false_positives": summary.false_positives,
        "false_negatives": summary.false_negatives,
        "precision": summary.precision,
        "recall": summary.recall,
        **_distance_summary(distances),
    }


def _planar_summary(document: Any, supported_ids: set[str]) -> dict[str, float | int]:
    matches = [match for match in document.matches if match.ground_truth_id in supported_ids]
    true_positives = len(matches)
    ground_truth_count = len(supported_ids)
    false_negatives = ground_truth_count - true_positives
    return {
        "ground_truth_count": ground_truth_count,
        "candidate_count": document.summary.num_candidates,
        "true_positives": true_positives,
        "false_negatives": false_negatives,
        "recall": true_positives / ground_truth_count if ground_truth_count else 0.0,
        **_distance_summary([match.distance_mm for match in matches]),
    }


def _supported_ids(adjudication: dict[str, Any], truth_ids: set[str]) -> set[str]:
    rows = adjudication.get("points")
    if not isinstance(rows, list):
        raise OperatingFrontierError("planar adjudication must contain points[]")
    row_ids = _unique_ids(
        (row.get("ground_truth_id", "") for row in rows if isinstance(row, dict)),
        "adjudication ground-truth",
    )
    if row_ids != truth_ids:
        missing = sorted(truth_ids - row_ids)
        extra = sorted(row_ids - truth_ids)
        raise OperatingFrontierError(
            "planar adjudication must cover exactly the evaluated truth ids "
            f"(missing={missing[:3]}, extra={extra[:3]})"
        )
    return {
        row["ground_truth_id"]
        for row in rows
        if isinstance(row, dict) and row.get("status") == "planar_supported"
    }


def _annotate_pareto(prefixes: list[dict[str, Any]]) -> None:
    """Attach a deterministic Pareto witness to each prefix.

    Objectives are full precision and planar-supported recall.  A single
    witness is sufficient to make every dominated relation traceable while
    avoiding a quadratic-sized JSON list of all pair relations.
    """
    for target in prefixes:
        target_precision = target["full"]["precision"]
        target_recall = target["planar_supported"]["recall"]
        witnesses = [
            candidate
            for candidate in prefixes
            if (
                candidate["full"]["precision"] >= target_precision
                and candidate["planar_supported"]["recall"] >= target_recall
                and (
                    candidate["full"]["precision"] > target_precision
                    or candidate["planar_supported"]["recall"] > target_recall
                )
            )
        ]
        witness = min(witnesses, key=lambda item: item["K"]) if witnesses else None
        target["pareto"] = {
            "objectives": ["full.precision", "planar_supported.recall"],
            "nondominated": witness is None,
            "dominated_by_K": witness["K"] if witness is not None else None,
        }


def build_operating_frontier(
    ground_truth: GroundTruthDocument,
    candidates: CandidatesDocument,
    adjudication: dict[str, Any],
    *,
    ordering_name: str,
    tolerance_mm: float = PRIMARY_TOLERANCE_MM,
    planar_recall_target: float = PLANAR_SUPPORTED_RECALL_TARGET,
) -> dict[str, Any]:
    """Evaluate every non-empty prefix of one fixed candidate ordering."""
    truth_ids = _unique_ids((point.id for point in ground_truth.points), "ground-truth")
    candidate_ids = [candidate.id for candidate in candidates.candidates]
    _unique_ids(candidate_ids, "candidate")
    supported_ids = _supported_ids(adjudication, truth_ids)
    required_tp = ceil(len(supported_ids) * planar_recall_target)

    prefixes: list[dict[str, Any]] = []
    for candidate_count in range(1, len(candidates.candidates) + 1):
        prefix_candidates = CandidatesDocument(
            meta=candidates.meta,
            candidates=candidates.candidates[:candidate_count],
        )
        result = evaluate(ground_truth, prefix_candidates, tolerance_mm=tolerance_mm)
        prefixes.append(
            {
                "K": candidate_count,
                "full": _full_summary(result),
                "planar_supported": _planar_summary(result, supported_ids),
            }
        )
    _annotate_pareto(prefixes)
    k_star = next(
        (
            item["K"]
            for item in prefixes
            if item["planar_supported"]["true_positives"] >= required_tp
        ),
        None,
    )
    return {
        "format_version": 1,
        "scope": "offline_operating_frontier",
        "evaluation_only": True,
        "matching": "greedy_nearest_distance_one_to_one",
        "primary_tolerance_mm": tolerance_mm,
        "ordering": {
            "name": ordering_name,
            "candidate_count": len(candidate_ids),
            "candidate_ids": candidate_ids,
        },
        "operating_point": {
            "definition": "first prefix whose planar-supported true positives meet the target",
            "planar_supported_recall_target": planar_recall_target,
            "required_planar_supported_true_positives": required_tp,
            "K_star": k_star,
        },
        "prefixes": prefixes,
    }


def compare_same_pool_frontiers(
    new_frontier: dict[str, Any], legacy_frontier: dict[str, Any], k: int
) -> dict[str, Any]:
    """Compare two orderings only when they contain exactly the same stations."""
    new_ids = new_frontier.get("ordering", {}).get("candidate_ids")
    legacy_ids = legacy_frontier.get("ordering", {}).get("candidate_ids")
    if not isinstance(new_ids, list) or not isinstance(legacy_ids, list):
        raise OperatingFrontierError("frontiers must retain their candidate-id pools")
    if len(new_ids) != len(legacy_ids) or set(new_ids) != set(legacy_ids):
        raise OperatingFrontierError("cannot compare frontiers with different candidate pools")

    def prefix(frontier: dict[str, Any]) -> dict[str, Any]:
        for item in frontier.get("prefixes", []):
            if item.get("K") == k:
                return item
        raise OperatingFrontierError(f"frontier has no prefix K={k}")

    return {
        "same_pool": True,
        "K": k,
        "new": prefix(new_frontier),
        "legacy": prefix(legacy_frontier),
    }


def historical_operating_frontier(source_run: str) -> dict[str, Any]:
    """Return the immutable RW01 observations without replaying old inputs."""
    full_at_600 = {
        "ground_truth_count": 286,
        "candidate_count": 600,
        "true_positives": 101,
        "false_positives": 499,
        "false_negatives": 185,
        "precision": 101 / 600,
        "recall": 101 / 286,
    }
    planar_at_600 = {
        "ground_truth_count": 97,
        "candidate_count": 600,
        "true_positives": 45,
        "false_negatives": 52,
        "recall": 45 / 97,
    }
    return {
        "format_version": 1,
        "scope": "offline_operating_frontier_historical_baseline",
        "evaluation_only": True,
        "historical_only": True,
        "source_run": source_run,
        "primary_tolerance_mm": PRIMARY_TOLERANCE_MM,
        "frozen_observations": {
            "candidate_count_600": {
                "full": full_at_600,
                "planar_supported": planar_at_600,
            },
            "legacy_interface_balanced_counterfactual": {
                "800": {"planar_supported_true_positives": 53, "planar_supported_recall": 53 / 97},
                "1000": {"planar_supported_true_positives": 57, "planar_supported_recall": 57 / 97},
                "1628": {"planar_supported_true_positives": 68, "planar_supported_recall": 68 / 97},
            },
        },
        "limitations": [
            "Historical observations are frozen evidence, not a reconstructed all-prefix frontier.",
            "Same-pool comparison is required before using any later ordering comparison for acceptance.",
        ],
    }


def operating_frontier_markdown(frontier: dict[str, Any]) -> str:
    """Render a compact human-readable companion without hiding the JSON data."""
    lines = ["# Weld operating frontier", "", "Scope: evaluation-only.", ""]
    if frontier.get("historical_only"):
        observations = frontier["frozen_observations"]
        current = observations["candidate_count_600"]
        lines += [
            "## Frozen historical observations",
            "",
            "| K | full TP / FP / FN | full precision | planar TP / FN | planar recall |",
            "|---:|---:|---:|---:|---:|",
            (
                "| 600 | "
                f"{current['full']['true_positives']} / {current['full']['false_positives']} / {current['full']['false_negatives']} | "
                f"{current['full']['precision']:.2%} | "
                f"{current['planar_supported']['true_positives']} / {current['planar_supported']['false_negatives']} | "
                f"{current['planar_supported']['recall']:.2%} |"
            ),
            "",
            "Legacy interface-balanced planar TP: "
            + ", ".join(
                f"K={k}: {row['planar_supported_true_positives']}"
                for k, row in observations["legacy_interface_balanced_counterfactual"].items()
            ),
            "",
        ]
        return "\n".join(lines)

    operating_point = frontier["operating_point"]
    lines += [
        "## Operating point",
        "",
        f"- Ordering: `{frontier['ordering']['name']}`",
        f"- K*: {operating_point['K_star'] if operating_point['K_star'] is not None else 'not reached'}",
        (
            "- Target: "
            f"{operating_point['required_planar_supported_true_positives']} planar-supported TP "
            f"({operating_point['planar_supported_recall_target']:.0%} recall)"
        ),
        "",
        "## Pareto prefixes",
        "",
        "| K | full precision | planar TP / FN | planar recall |",
        "|---:|---:|---:|---:|",
    ]
    for prefix in frontier["prefixes"]:
        if prefix["pareto"]["nondominated"]:
            planar = prefix["planar_supported"]
            lines.append(
                f"| {prefix['K']} | {prefix['full']['precision']:.2%} | "
                f"{planar['true_positives']} / {planar['false_negatives']} | {planar['recall']:.2%} |"
            )
    lines.append("")
    return "\n".join(lines)
