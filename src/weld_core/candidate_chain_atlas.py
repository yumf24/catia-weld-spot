"""Evaluation-only causal evidence for every planar-supported weld truth.

The atlas joins already-published production audits with explicitly offline
truth, adjudication, and point-matching reports.  It is deliberately not a
candidate-generation dependency: no selector, layout, ranking, or CATIA
write-back module imports this file.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .schema import CandidatesDocument


class CandidateChainAtlasError(ValueError):
    """Raised when the published audit trail cannot prove a causal state."""


FN_REASONS = (
    "region_build_failed",
    "layout_empty",
    "pool_coverage_gap",
    "ranked_after_k",
    "match_collision",
    "match_offset",
)


def canonical_interface_id(value: str | dict[str, Any]) -> str:
    """Return the stable interface ID from either supported wire encoding."""
    if isinstance(value, str):
        return value
    try:
        return f"{value['face_a_id']}::{value['face_b_id']}"
    except (KeyError, TypeError) as exc:
        raise CandidateChainAtlasError(f"invalid supporting-interface evidence: {value!r}") from exc


def supporting_interface_ids(adjudication: dict[str, Any]) -> set[str]:
    """Return all direct interface references used by planar-supported truth."""
    points = adjudication.get("points")
    if not isinstance(points, list):
        raise CandidateChainAtlasError("planar adjudication must contain points[]")
    return {
        canonical_interface_id(interface)
        for point in points
        if point.get("status") == "planar_supported"
        for interface in point.get("supporting_interfaces", [])
    }


def load_selected_pair_audit(path: str | Path, wanted_ids: set[str]) -> dict[str, dict[str, Any]]:
    """Stream only the required records from a potentially multi-GB pair audit.

    Pair audits are a single JSON document with a very large ``pairs`` array.
    Loading the complete file merely to inspect the handful of interfaces that
    support adjudicated truth is unnecessary and can exhaust a normal desktop.
    """
    source = Path(path)
    decoder = json.JSONDecoder()
    chunk_size = 1024 * 1024
    with source.open(encoding="utf-8") as stream:
        buffer = ""
        while '"pairs"' not in buffer:
            chunk = stream.read(chunk_size)
            if not chunk:
                raise CandidateChainAtlasError(f"pair audit {source} has no pairs array")
            buffer += chunk
        position = buffer.index('"pairs"') + len('"pairs"')
        while True:
            if position >= len(buffer):
                chunk = stream.read(chunk_size)
                if not chunk:
                    raise CandidateChainAtlasError(f"pair audit {source} has an incomplete pairs array")
                buffer += chunk
            if buffer[position] == "[":
                position += 1
                break
            position += 1

        selected: dict[str, dict[str, Any]] = {}
        while True:
            while True:
                if position >= len(buffer):
                    buffer = buffer[position:] + stream.read(chunk_size)
                    position = 0
                    if not buffer:
                        raise CandidateChainAtlasError(f"pair audit {source} has an incomplete pairs array")
                if buffer[position].isspace() or buffer[position] == ",":
                    position += 1
                    continue
                break
            if buffer[position] == "]":
                break
            try:
                row, position = decoder.raw_decode(buffer, position)
            except json.JSONDecodeError:
                # Keep the incomplete object and append another chunk.
                buffer = buffer[position:] + stream.read(chunk_size)
                position = 0
                continue
            if isinstance(row, dict) and row.get("id") in wanted_ids:
                selected[row["id"]] = row
            if position > chunk_size:
                buffer = buffer[position:]
                position = 0
    missing = sorted(wanted_ids - selected.keys())
    if missing:
        raise CandidateChainAtlasError(f"pair audit is missing supporting interfaces: {missing[:3]}")
    return selected


def _distance(left: Iterable[float], right: Iterable[float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right)) ** 0.5


def _by_interface(rows: Iterable[dict[str, Any]], key: str = "supporting_interfaces") -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for interface in row.get(key, []):
            result[interface].append(row)
    return result


def _direct_rows(by_interface: dict[str, list[dict[str, Any]]], interface_ids: set[str]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for interface_id in sorted(interface_ids):
        for row in by_interface.get(interface_id, []):
            identity = str(row.get("candidate_id") or row.get("source_candidate_id") or row.get("representative_candidate_id") or id(row))
            if identity not in seen:
                seen.add(identity)
                result.append(row)
    return result


def _selector_reason(records: list[dict[str, Any]]) -> str:
    reasons = {row.get("reason") or "unspecified" for row in records}
    if len(reasons) != 1:
        raise CandidateChainAtlasError(f"selector rejected supporting interfaces for multiple reasons: {sorted(reasons)}")
    return f"selector_rejected:{reasons.pop()}"


def _legacy_reason(
    attribution: str | None,
    selector_records: list[dict[str, Any]],
    layouts: list[dict[str, Any]],
) -> str | None:
    """Translate only the legacy report's named state to the new vocabulary.

    This branch exists to make the historical RW01 run reproducible.  New
    runs are classified from the direct production evidence below instead.
    """
    if attribution == "budget_excluded":
        return "ranked_after_k"
    if attribution == "layout_offset":
        return "match_offset"
    if attribution == "region_not_covered":
        return "pool_coverage_gap"
    if attribution == "interface_not_found":
        if selector_records and not any(row.get("accepted") for row in selector_records):
            return _selector_reason(selector_records)
        if layouts and all(int(row.get("retained_count", 0)) == 0 for row in layouts):
            return "layout_empty"
    return None


def _classify_false_negative(
    *,
    position: list[float],
    selector_records: list[dict[str, Any]],
    regions: list[dict[str, Any]],
    layouts: list[dict[str, Any]],
    physical_stations: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    budget_rows: list[dict[str, Any]],
    matched_candidate_to_truth: dict[str, str],
    legacy_attribution: str | None,
) -> str:
    legacy = _legacy_reason(legacy_attribution, selector_records, layouts)
    if legacy is not None:
        return legacy
    if not selector_records:
        raise CandidateChainAtlasError("missing selector decision for planar-supported interface")
    if not any(row.get("accepted") for row in selector_records):
        return _selector_reason(selector_records)
    if not regions:
        return "region_build_failed"
    if not layouts or all(int(row.get("retained_count", 0)) == 0 for row in layouts):
        return "layout_empty"
    if not physical_stations:
        return "pool_coverage_gap"
    if not candidate_rows:
        if any(row.get("status") == "budget_excluded" for row in budget_rows):
            return "ranked_after_k"
        return "pool_coverage_gap"
    if any(row["candidate_id"] in matched_candidate_to_truth for row in candidate_rows):
        return "match_collision"
    # Candidate rows are direct interface evidence.  A mismatch here is an
    # offset, never a guess from unrelated spatially-near candidates.
    return "match_offset"


def _assert_summary_conservation(evaluation: dict[str, Any], errors: dict[str, Any]) -> None:
    expected = evaluation.get("summary", {})
    reported = errors.get("summary", {})
    for field in ("true_positives", "false_positives", "false_negatives"):
        if expected.get(field) != reported.get(field):
            raise CandidateChainAtlasError(f"evaluation and error analysis disagree on {field}")
    arrays = {
        "true_positives": errors.get("true_positives", []),
        "false_positives": errors.get("false_positives", []),
        "false_negatives": errors.get("false_negatives", []),
    }
    for field, rows in arrays.items():
        if reported.get(field) != len(rows):
            raise CandidateChainAtlasError(f"error analysis {field} count is not traceable")


def build_candidate_chain_atlas(
    *,
    candidates: CandidatesDocument,
    adjudication: dict[str, Any],
    evaluation: dict[str, Any],
    error_analysis: dict[str, Any],
    pair_records: dict[str, dict[str, Any]],
    interface_region_audit: dict[str, Any],
    coverage_layout_audit: dict[str, Any],
    candidate_budget_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build causal rows for every planar-supported truth point.

    Associations are exclusively through supporting interface IDs, exact-region
    references, or physical-station sources.  Position is used only to report
    a direct station's already-associated offset; it never creates an
    interface association from an arbitrary neighbouring candidate.
    """
    _assert_summary_conservation(evaluation, error_analysis)
    adjudicated = {
        row["ground_truth_id"]: row
        for row in adjudication.get("points", [])
        if row.get("status") == "planar_supported"
    }
    if len(adjudicated) != evaluation.get("planar_supported_summary", {}).get("ground_truth_count"):
        raise CandidateChainAtlasError("planar-supported denominator disagrees with evaluation")
    missing_pairs = supporting_interface_ids(adjudication) - pair_records.keys()
    if missing_pairs:
        raise CandidateChainAtlasError(f"missing pair evidence for supporting interfaces: {sorted(missing_pairs)[:3]}")

    regions = {row["id"]: row for row in interface_region_audit.get("regions", []) if row.get("id")}
    layouts = {row["interface_id"]: row for row in coverage_layout_audit.get("interfaces", []) if row.get("interface_id")}
    layout_samples_by_interface = _by_interface(coverage_layout_audit.get("original_exact_layout_points", []), "source_interfaces")
    physical_by_interface = _by_interface(coverage_layout_audit.get("physical_stations", []))
    budget_by_interface = _by_interface((candidate_budget_audit or {}).get("stations", []))
    candidate_rank = {candidate.id: rank for rank, candidate in enumerate(candidates.candidates, start=1)}
    candidate_rows_by_interface = _by_interface(
        [
            {
                "candidate_id": candidate.id,
                "rank": candidate_rank[candidate.id],
                "position_mm": list(candidate.position),
                "supporting_interfaces": candidate.supporting_interfaces,
                "layer_count": candidate.layer_count,
                "confidence_tier": candidate.confidence_tier,
                "exact_region_refs": candidate.exact_region_refs,
            }
            for candidate in candidates.candidates
        ]
    )
    matches = {row["ground_truth_id"]: row for row in error_analysis.get("true_positives", [])}
    matched_candidate_to_truth = {row["candidate_id"]: row["ground_truth_id"] for row in matches.values()}
    false_negative_attribution = {
        row["ground_truth_id"]: row.get("attribution") for row in error_analysis.get("false_negatives", [])
    }

    points: list[dict[str, Any]] = []
    for truth_id in sorted(adjudicated):
        truth = adjudicated[truth_id]
        interfaces = {canonical_interface_id(item) for item in truth.get("supporting_interfaces", [])}
        selector_records = [pair_records[interface] for interface in sorted(interfaces)]
        region_rows = [regions[interface] for interface in sorted(interfaces) if interface in regions]
        layout_rows = [layouts[interface] for interface in sorted(interfaces) if interface in layouts]
        layout_samples = _direct_rows(layout_samples_by_interface, interfaces)
        physical_rows = _direct_rows(physical_by_interface, interfaces)
        budget_rows = _direct_rows(budget_by_interface, interfaces)
        candidate_rows = _direct_rows(candidate_rows_by_interface, interfaces)
        match = matches.get(truth_id)
        if match is None:
            reason = _classify_false_negative(
                position=truth["position_mm"],
                selector_records=selector_records,
                regions=region_rows,
                layouts=layout_rows,
                physical_stations=physical_rows,
                candidate_rows=candidate_rows,
                budget_rows=budget_rows,
                matched_candidate_to_truth=matched_candidate_to_truth,
                legacy_attribution=false_negative_attribution.get(truth_id),
            )
            state = "false_negative"
            prefix_hit = {"matched": False, "candidate_id": None, "rank": None}
        else:
            reason = None
            state = "matched"
            prefix_hit = {
                "matched": True,
                "candidate_id": match["candidate_id"],
                "rank": candidate_rank.get(match["candidate_id"]),
            }
        points.append(
            {
                "ground_truth_id": truth_id,
                "position_mm": truth["position_mm"],
                "supporting_interfaces": sorted(interfaces),
                "selector": [
                    {
                        "interface_id": row["id"],
                        "accepted": row.get("accepted"),
                        "reason": row.get("reason"),
                        "common_area_mm2": row.get("common_area_mm2"),
                        "coverage_a": row.get("coverage_a"),
                        "coverage_b": row.get("coverage_b"),
                    }
                    for row in selector_records
                ],
                "exact_regions": [
                    {
                        "interface_id": row["id"],
                        "geometry_ref": row.get("geometry_ref"),
                        "common_area_mm2": row.get("common_area_mm2"),
                    }
                    for row in region_rows
                ],
                "layout": {
                    "interfaces": layout_rows,
                    "samples": layout_samples,
                },
                "physical_stations": physical_rows,
                "ranking": {
                    "candidates": candidate_rows,
                    "budget_stations": budget_rows,
                },
                "prefix_hit": prefix_hit,
                "matching": match,
                "causal_state": state,
                "false_negative_reason": reason,
                "legacy_evaluation_attribution": false_negative_attribution.get(truth_id),
            }
        )

    reasons = Counter(point["false_negative_reason"] for point in points if point["causal_state"] == "false_negative")
    planar_tp = sum(point["causal_state"] == "matched" for point in points)
    planar_summary = evaluation["planar_supported_summary"]
    if planar_tp != planar_summary["true_positives"] or sum(reasons.values()) != planar_summary["false_negatives"]:
        raise CandidateChainAtlasError("planar-supported causal counts do not conserve the evaluation denominator")
    return {
        "format_version": 1,
        "scope": "offline_candidate_chain_atlas",
        "evaluation_only": True,
        "matching": evaluation.get("matching"),
        "primary_tolerance_mm": evaluation.get("primary_tolerance_mm"),
        "summary": {
            "full": evaluation["summary"],
            "planar_supported": planar_summary,
            "planar_causal_counts": dict(sorted(reasons.items())),
            "conservation": {
                "planar_supported_true_positives": planar_tp,
                "planar_supported_false_negative_reasons": sum(reasons.values()),
                "planar_supported_total": planar_tp + sum(reasons.values()),
            },
        },
        "points": points,
    }


def candidate_chain_atlas_markdown(atlas: dict[str, Any]) -> str:
    """Render a compact companion that exposes the causal-count conservation."""
    summary = atlas["summary"]
    lines = [
        "# Weld candidate-chain atlas",
        "",
        "Scope: evaluation-only.",
        "",
        "## Conservation",
        "",
        f"- Full TP / FP / FN: {summary['full']['true_positives']} / {summary['full']['false_positives']} / {summary['full']['false_negatives']}",
        (
            "- Planar-supported TP + FN reasons = "
            f"{summary['conservation']['planar_supported_true_positives']} + "
            f"{summary['conservation']['planar_supported_false_negative_reasons']} = "
            f"{summary['conservation']['planar_supported_total']}"
        ),
        "",
        "## Planar false-negative causes",
        "",
        "| cause | count |",
        "|---|---:|",
    ]
    lines.extend(f"| `{reason}` | {count} |" for reason, count in summary["planar_causal_counts"].items())
    lines.append("")
    return "\n".join(lines)
