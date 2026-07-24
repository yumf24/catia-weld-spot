from __future__ import annotations

import copy
import json

from weld_core.candidate_chain_atlas import (
    build_candidate_chain_atlas,
    load_selected_pair_audit,
    supporting_interface_ids,
)
from weld_core.schema import Candidate, CandidatesDocument


def _summary(true_positives: int, false_positives: int, false_negatives: int) -> dict:
    return {
        "ground_truth_count": true_positives + false_negatives,
        "candidate_count": true_positives + false_positives,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": true_positives / (true_positives + false_positives),
        "recall": true_positives / (true_positives + false_negatives),
    }


def _fixture():
    interface_by_truth = {
        "gt-match": ["i-collision-a", "i-collision-b"],
        "gt-selector": ["i-selector"],
        "gt-region": ["i-region"],
        "gt-layout": ["i-layout"],
        "gt-pool": ["i-pool"],
        "gt-ranked": ["i-ranked"],
        "gt-collision": ["i-collision-a", "i-collision-b"],
        "gt-offset": ["i-offset"],
    }
    positions = {truth_id: [index * 10.0, 0.0, 0.0] for index, truth_id in enumerate(interface_by_truth)}
    adjudication = {"points": [
        {
            "ground_truth_id": truth_id,
            "position_mm": positions[truth_id],
            "status": "planar_supported",
            "supporting_interfaces": interfaces,
        }
        for truth_id, interfaces in interface_by_truth.items()
    ]}
    pair_records = {
        interface_id: {
            "id": interface_id,
            "accepted": interface_id != "i-selector",
            "reason": "coverage_below_threshold" if interface_id == "i-selector" else None,
            "common_area_mm2": 200.0,
            "coverage_a": 0.5,
            "coverage_b": 0.5,
        }
        for interfaces in interface_by_truth.values()
        for interface_id in interfaces
    }
    regions = [
        {"id": interface_id, "geometry_ref": f"exact/{interface_id}.brep", "common_area_mm2": 200.0}
        for interface_id in pair_records
        if interface_id not in {"i-selector", "i-region"}
    ]
    layout_interfaces = [
        {"interface_id": interface_id, "retained_count": 0 if interface_id == "i-layout" else 1}
        for interface_id in pair_records
        if interface_id not in {"i-selector", "i-region"}
    ]
    physical = [
        {"representative_candidate_id": "station-ranked", "position_mm": positions["gt-ranked"], "supporting_interfaces": ["i-ranked"]},
        {"representative_candidate_id": "station-collision", "position_mm": positions["gt-collision"], "supporting_interfaces": ["i-collision-a", "i-collision-b"]},
        {"representative_candidate_id": "station-offset", "position_mm": [999.0, 0.0, 0.0], "supporting_interfaces": ["i-offset"]},
    ]
    candidates = CandidatesDocument(candidates=[
        Candidate(id="c-collision", position=tuple(positions["gt-match"]), supporting_interfaces=["i-collision-a", "i-collision-b"]),
        Candidate(id="c-offset", position=(999.0, 0.0, 0.0), supporting_interfaces=["i-offset"]),
    ])
    error_analysis = {
        "summary": _summary(1, 1, 7),
        "true_positives": [{"ground_truth_id": "gt-match", "candidate_id": "c-collision", "distance_mm": 0.0}],
        "false_positives": [{"candidate_id": "c-offset"}],
        "false_negatives": [{"ground_truth_id": truth_id} for truth_id in interface_by_truth if truth_id != "gt-match"],
    }
    evaluation = {
        "matching": "greedy_nearest_distance_one_to_one",
        "primary_tolerance_mm": 10.0,
        "summary": _summary(1, 1, 7),
        "planar_supported_summary": {"ground_truth_count": 8, "candidate_count": 2, "true_positives": 1, "false_negatives": 7, "recall": 0.125},
    }
    coverage = {"interfaces": layout_interfaces, "original_exact_layout_points": [], "physical_stations": physical}
    budget = {"stations": [
        {"source_candidate_id": "station-ranked", "position_mm": positions["gt-ranked"], "supporting_interfaces": ["i-ranked"], "status": "budget_excluded"},
        {"source_candidate_id": "station-collision", "candidate_id": "c-collision", "position_mm": positions["gt-collision"], "supporting_interfaces": ["i-collision-a", "i-collision-b"], "status": "selected"},
        {"source_candidate_id": "station-offset", "candidate_id": "c-offset", "position_mm": [999.0, 0.0, 0.0], "supporting_interfaces": ["i-offset"], "status": "selected"},
    ]}
    return {
        "candidates": candidates,
        "adjudication": adjudication,
        "evaluation": evaluation,
        "error_analysis": error_analysis,
        "pair_records": pair_records,
        "interface_region_audit": {"regions": regions},
        "coverage_layout_audit": coverage,
        "candidate_budget_audit": budget,
    }


def test_candidate_chain_atlas_covers_all_seven_mutually_exclusive_causal_states():
    atlas = build_candidate_chain_atlas(**_fixture())

    rows = {row["ground_truth_id"]: row for row in atlas["points"]}
    assert rows["gt-match"]["causal_state"] == "matched"
    assert rows["gt-selector"]["false_negative_reason"] == "selector_rejected:coverage_below_threshold"
    assert rows["gt-region"]["false_negative_reason"] == "region_build_failed"
    assert rows["gt-layout"]["false_negative_reason"] == "layout_empty"
    assert rows["gt-pool"]["false_negative_reason"] == "pool_coverage_gap"
    assert rows["gt-ranked"]["false_negative_reason"] == "ranked_after_k"
    assert rows["gt-collision"]["false_negative_reason"] == "match_collision"
    assert rows["gt-offset"]["false_negative_reason"] == "match_offset"
    assert atlas["summary"]["conservation"] == {
        "planar_supported_true_positives": 1,
        "planar_supported_false_negative_reasons": 7,
        "planar_supported_total": 8,
    }
    assert rows["gt-collision"]["ranking"]["candidates"][0]["candidate_id"] == "c-collision"
    assert rows["gt-collision"]["prefix_hit"] == {"matched": False, "candidate_id": None, "rank": None}


def test_interface_order_does_not_change_direct_evidence_or_causal_reason():
    fixture = _fixture()
    reversed_fixture = copy.deepcopy(fixture)
    for point in reversed_fixture["adjudication"]["points"]:
        point["supporting_interfaces"].reverse()

    normal = build_candidate_chain_atlas(**fixture)
    reversed_atlas = build_candidate_chain_atlas(**reversed_fixture)
    assert normal["points"] == reversed_atlas["points"]


def test_pair_audit_reader_streams_only_directly_referenced_interfaces(tmp_path):
    audit_path = tmp_path / "pair_audit.json"
    audit_path.write_text(json.dumps({"format_version": 1, "pairs": [
        {"id": "discard", "accepted": False},
        {"id": "keep", "accepted": True, "reason": None},
    ]}), encoding="utf-8")

    assert load_selected_pair_audit(audit_path, {"keep"}) == {
        "keep": {"id": "keep", "accepted": True, "reason": None},
    }
    assert supporting_interface_ids({"points": [{
        "status": "planar_supported", "supporting_interfaces": [{"face_a_id": "a", "face_b_id": "b"}],
    }]}) == {"a::b"}
