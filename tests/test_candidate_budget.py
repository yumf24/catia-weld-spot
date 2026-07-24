from weld_core.candidate_budget import select_interface_balanced_candidates
from weld_core.config import WeldParams
from weld_core.schema import Candidate


def _candidate(candidate_id, position, interfaces):
    return Candidate(id=candidate_id, position=position, faces=["A/f", "B/f"], supporting_interfaces=interfaces)


def test_budget_seeds_each_interface_then_balances_farthest_points():
    candidates = [
        _candidate("a0", (0, 0, 0), ["a"]), _candidate("a1", (100, 0, 0), ["a"]),
        _candidate("b0", (0, 10, 0), ["b"]), _candidate("b1", (100, 10, 0), ["b"]),
    ]
    selected, audit = select_interface_balanced_candidates(candidates, WeldParams(candidate_budget_target=3))
    assert {interface for candidate in selected for interface in candidate.supporting_interfaces} == {"a", "b"}
    assert len(selected) == audit["selected_count"] == 3
    assert {row["status"] for row in audit["stations"]} == {"selected", "budget_excluded"}


def test_budget_is_stable_when_input_order_changes_and_hits_target():
    candidates = [
        _candidate(f"a{index}", (index * 10, 0, 0), ["a"])
        for index in range(8)
    ] + [
        _candidate(f"b{index}", (index * 10, 10, 0), ["b"])
        for index in range(8)
    ]
    params = WeldParams(candidate_budget_target=6)
    forward, _ = select_interface_balanced_candidates(candidates, params)
    reversed_, _ = select_interface_balanced_candidates(list(reversed(candidates)), params)
    assert [candidate.id for candidate in forward] == [candidate.id for candidate in reversed_]
    assert len(forward) == 6
