from weld_core.config import WeldParams
from weld_core.multilayer_candidates import aggregate_multilayer_candidates
from weld_core.schema import Candidate


def _candidate(candidate_id, position, faces, interface):
    return Candidate(
        id=candidate_id, position=position, faces=faces, layer_type="two_layer",
        supporting_interfaces=[interface], confidence_tier="high", exact_region_refs=[interface + ".brep"],
    )


def test_colocated_interfaces_sharing_a_part_become_a_three_layer_connection():
    candidates, audit = aggregate_multilayer_candidates([
        _candidate("ab", (0, 0, 0), ["A/top", "B/bottom"], "A::B"),
        _candidate("bc", (0.04, 0, 0), ["B/top", "C/bottom"], "B::C"),
    ], WeldParams())

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.layer_type == "three_layer"
    assert candidate.layer_count == 3
    assert candidate.supporting_interfaces == ["A::B", "B::C"]
    assert candidate.confidence_tier == "high"
    assert audit[0]["status"] == "aggregated"


def test_four_part_stack_retains_actual_layer_count_and_independent_interfaces_remain():
    stack, _ = aggregate_multilayer_candidates([
        _candidate("ab", (0, 0, 0), ["A/f", "B/f"], "A::B"),
        _candidate("bc", (0.04, 0, 0), ["B/f", "C/f"], "B::C"),
        _candidate("cd", (0.02, 0, 0), ["C/f", "D/f"], "C::D"),
    ], WeldParams())
    assert len(stack) == 1 and stack[0].layer_count == 4 and stack[0].layer_type == "three_layer"

    independent, _ = aggregate_multilayer_candidates([
        _candidate("ab", (0, 0, 0), ["A/f", "B/f"], "A::B"),
        _candidate("cd", (0.04, 0, 0), ["C/f", "D/f"], "C::D"),
    ], WeldParams())
    assert len(independent) == 2
