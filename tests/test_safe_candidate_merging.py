from weld_core.candidate_merging import safe_merge_candidates
from weld_core.config import WeldParams
from weld_core.schema import Candidate


def _candidate(candidate_id, position, faces):
    return Candidate(id=candidate_id, position=position, faces=faces, layer_type="two_layer", reason="test")


def test_nearby_independent_interfaces_are_not_merged():
    candidates, audit = safe_merge_candidates(
        [_candidate("a", (0, 0, 0), ["A", "B"]), _candidate("b", (1, 0, 0), ["C", "D"])], WeldParams()
    )
    assert [candidate.id for candidate in candidates] == ["a", "b"]
    assert [row["status"] for row in audit] == ["retained", "retained"]


def test_colocated_candidates_for_same_interface_are_merged_with_audit():
    candidates, audit = safe_merge_candidates(
        [_candidate("a", (0, 0, 0), ["A", "B"]), _candidate("b", (0.04, 0, 0), ["B", "A"])], WeldParams()
    )
    assert [candidate.id for candidate in candidates] == ["a"]
    assert audit[-1]["status"] == "merged"
    assert audit[-1]["into_candidate_id"] == "a"


def test_same_interface_layout_points_14mm_apart_are_not_merged():
    candidates, audit = safe_merge_candidates(
        [_candidate("a", (0, 0, 0), ["A", "B"]), _candidate("b", (10, 10, 0), ["A", "B"])], WeldParams()
    )
    assert [candidate.id for candidate in candidates] == ["a", "b"]
    assert [row["status"] for row in audit] == ["retained", "retained"]
