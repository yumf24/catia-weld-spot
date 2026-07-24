from __future__ import annotations

import pytest

from weld_core.operating_frontier import (
    OperatingFrontierError,
    build_operating_frontier,
    compare_same_pool_frontiers,
    historical_operating_frontier,
)
from weld_core.schema import Candidate, CandidatesDocument, GroundTruthDocument, GroundTruthPoint


def _truth() -> GroundTruthDocument:
    return GroundTruthDocument(points=[
        GroundTruthPoint(id="gt-supported-1", position=(0, 0, 0)),
        GroundTruthPoint(id="gt-supported-2", position=(10, 0, 0)),
        GroundTruthPoint(id="gt-unresolved", position=(20, 0, 0)),
    ])


def _adjudication() -> dict:
    return {"points": [
        {"ground_truth_id": "gt-supported-1", "status": "planar_supported"},
        {"ground_truth_id": "gt-supported-2", "status": "planar_supported"},
        {"ground_truth_id": "gt-unresolved", "status": "out_of_scope_or_unresolved"},
    ]}


def _candidates(ids: tuple[str, ...] = ("c-1", "c-extra", "c-2")) -> CandidatesDocument:
    positions = {
        "c-1": (0, 0, 0),
        "c-extra": (100, 0, 0),
        "c-2": (10, 0, 0),
        "c-other": (200, 0, 0),
    }
    return CandidatesDocument(candidates=[
        Candidate(id=candidate_id, position=positions[candidate_id])
        for candidate_id in ids
    ])


def test_frontier_publishes_every_prefix_k_star_and_pareto_relation():
    frontier = build_operating_frontier(
        _truth(), _candidates(), _adjudication(), ordering_name="fixture-order",
    )

    assert [row["K"] for row in frontier["prefixes"]] == [1, 2, 3]
    assert frontier["operating_point"] == {
        "definition": "first prefix whose planar-supported true positives meet the target",
        "planar_supported_recall_target": 0.8,
        "required_planar_supported_true_positives": 2,
        "K_star": 3,
    }
    first, middle, last = frontier["prefixes"]
    assert first["full"]["true_positives"] == 1
    assert first["full"]["precision"] == 1.0
    assert first["planar_supported"]["recall"] == 0.5
    assert middle["pareto"] == {
        "objectives": ["full.precision", "planar_supported.recall"],
        "nondominated": False,
        "dominated_by_K": 1,
    }
    assert last["planar_supported"]["true_positives"] == 2
    assert last["planar_supported"]["false_negatives"] == 0
    assert last["planar_supported"]["median_error_mm"] == 0.0


def test_same_pool_comparator_requires_the_identical_physical_station_pool():
    new_frontier = build_operating_frontier(
        _truth(), _candidates(), _adjudication(), ordering_name="new",
    )
    legacy_frontier = build_operating_frontier(
        _truth(), _candidates(("c-2", "c-extra", "c-1")), _adjudication(), ordering_name="legacy",
    )

    comparison = compare_same_pool_frontiers(new_frontier, legacy_frontier, 2)
    assert comparison["same_pool"] is True
    assert comparison["new"]["K"] == comparison["legacy"]["K"] == 2

    incompatible = build_operating_frontier(
        _truth(), _candidates(("c-1", "c-extra", "c-other")), _adjudication(), ordering_name="other",
    )
    with pytest.raises(OperatingFrontierError, match="different candidate pools"):
        compare_same_pool_frontiers(new_frontier, incompatible, 2)


def test_historical_frontier_freezes_the_rw01_observations():
    frontier = historical_operating_frontier("data/component-weld-evaluation/example")

    assert frontier["historical_only"] is True
    at_600 = frontier["frozen_observations"]["candidate_count_600"]
    assert at_600["full"] == {
        "ground_truth_count": 286,
        "candidate_count": 600,
        "true_positives": 101,
        "false_positives": 499,
        "false_negatives": 185,
        "precision": 101 / 600,
        "recall": 101 / 286,
    }
    counterfactual = frontier["frozen_observations"]["legacy_interface_balanced_counterfactual"]
    assert {key: value["planar_supported_true_positives"] for key, value in counterfactual.items()} == {
        "800": 53,
        "1000": 57,
        "1628": 68,
    }
