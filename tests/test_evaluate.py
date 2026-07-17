"""weld_core.evaluate tests -- pure numpy, no OCP/CATIA required."""

from __future__ import annotations

import pytest

from weld_core.evaluate import evaluate
from weld_core.schema import (
    Candidate,
    CandidatesDocument,
    GroundTruthDocument,
    GroundTruthPoint,
)


def _gt(*positions) -> GroundTruthDocument:
    return GroundTruthDocument(
        points=[
            GroundTruthPoint(id=f"gt_{i:03d}", position=p, radius=3.0)
            for i, p in enumerate(positions, start=1)
        ]
    )


def _cands(*positions) -> CandidatesDocument:
    return CandidatesDocument(
        candidates=[
            Candidate(id=f"wc_{i:03d}", position=p) for i, p in enumerate(positions, start=1)
        ]
    )


def test_perfect_match_all_true_positive():
    gt = _gt((0.0, 0.0, 0.0), (100.0, 0.0, 0.0))
    cand = _cands((0.0, 0.0, 0.0), (100.0, 0.0, 0.0))

    result = evaluate(gt, cand, tolerance_mm=5.0)

    assert result.summary.true_positives == 2
    assert result.summary.false_negatives == 0
    assert result.summary.false_positives == 0
    assert result.summary.recall == pytest.approx(1.0)
    assert result.summary.precision == pytest.approx(1.0)
    assert result.summary.mean_error_mm == pytest.approx(0.0)


def test_missed_ground_truth_point_is_false_negative():
    gt = _gt((0.0, 0.0, 0.0), (100.0, 0.0, 0.0))
    cand = _cands((0.0, 0.0, 0.0))  # second real weld point has no candidate nearby

    result = evaluate(gt, cand, tolerance_mm=5.0)

    assert result.summary.true_positives == 1
    assert result.summary.false_negatives == 1
    assert result.summary.false_positives == 0
    assert result.summary.recall == pytest.approx(0.5)
    assert result.summary.precision == pytest.approx(1.0)
    assert result.unmatched_ground_truth == ["gt_002"]


def test_extra_candidate_is_false_positive_but_recall_stays_full():
    gt = _gt((0.0, 0.0, 0.0))
    cand = _cands((0.0, 0.0, 0.0), (500.0, 0.0, 0.0))  # spurious extra candidate

    result = evaluate(gt, cand, tolerance_mm=5.0)

    assert result.summary.true_positives == 1
    assert result.summary.false_negatives == 0
    assert result.summary.false_positives == 1
    assert result.summary.recall == pytest.approx(1.0)
    assert result.summary.precision == pytest.approx(0.5)
    assert result.unmatched_candidates == ["wc_002"]


def test_tolerance_boundary_included_and_excluded():
    gt = _gt((0.0, 0.0, 0.0))

    just_inside = _cands((4.999, 0.0, 0.0))
    result_inside = evaluate(gt, just_inside, tolerance_mm=5.0)
    assert result_inside.summary.true_positives == 1

    just_outside = _cands((5.001, 0.0, 0.0))
    result_outside = evaluate(gt, just_outside, tolerance_mm=5.0)
    assert result_outside.summary.true_positives == 0
    assert result_outside.summary.false_negatives == 1
    assert result_outside.summary.false_positives == 1


def test_nearest_candidate_is_picked_when_multiple_are_within_tolerance():
    gt = _gt((0.0, 0.0, 0.0))
    cand = _cands((3.0, 0.0, 0.0), (1.0, 0.0, 0.0))  # wc_001 farther, wc_002 nearer

    result = evaluate(gt, cand, tolerance_mm=5.0)

    assert len(result.matches) == 1
    assert result.matches[0].candidate_id == "wc_002"
    assert result.matches[0].distance_mm == pytest.approx(1.0)
    assert result.unmatched_candidates == ["wc_001"]


def test_matching_is_one_to_one_not_many_to_one():
    """Two ground-truth points near one candidate: only the closer one claims it."""
    gt = _gt((0.0, 0.0, 0.0), (2.0, 0.0, 0.0))
    cand = _cands((0.5, 0.0, 0.0))

    result = evaluate(gt, cand, tolerance_mm=5.0)

    assert result.summary.true_positives == 1
    assert result.summary.false_negatives == 1
    assert result.matches[0].ground_truth_id == "gt_001"
    assert result.unmatched_ground_truth == ["gt_002"]


def test_empty_ground_truth_gives_full_precision_zero_recall_definition():
    gt = _gt()
    cand = _cands((0.0, 0.0, 0.0))

    result = evaluate(gt, cand, tolerance_mm=5.0)

    assert result.summary.recall == pytest.approx(1.0)  # no real points to miss
    assert result.summary.precision == pytest.approx(0.0)
    assert result.summary.false_positives == 1


def test_empty_candidates_gives_zero_recall():
    gt = _gt((0.0, 0.0, 0.0))
    cand = _cands()

    result = evaluate(gt, cand, tolerance_mm=5.0)

    assert result.summary.recall == pytest.approx(0.0)
    assert result.summary.precision == pytest.approx(1.0)  # no candidates to be wrong
    assert result.summary.false_negatives == 1
