from weld_core.component_weld_ansa import build_ansa_layers
from weld_core.schema import Candidate, CandidatesDocument


def test_old_candidate_json_remains_readable_with_safe_contract_defaults():
    document = CandidatesDocument.model_validate({"candidates": [{"id": "old", "position": [0, 0, 0], "faces": ["A", "B"], "layer_type": "two_layer"}]})
    candidate = document.candidates[0]
    assert (candidate.layer_count, candidate.supporting_interfaces, candidate.confidence_tier, candidate.exact_region_refs) == (2, [], "medium", [])


def test_low_confidence_is_preserved_in_ansa_candidate_marker_rows():
    layers = build_ansa_layers({
        "true_positives": [],
        "false_negatives": [],
        "false_positives": [{
            "candidate_id": "low-1", "candidate_position_mm": [1, 2, 3], "candidate_faces": ["A", "B"],
            "candidate_layer_count": 4, "candidate_supporting_interfaces": ["A::B", "B::C"],
            "candidate_confidence_tier": "low", "candidate_exact_region_refs": ["r.brep"],
        }],
    })
    marker = layers["FP_CANDIDATE"][0]
    assert marker["confidence_tier"] == "low"
    assert marker["layer_count"] == 4
    assert marker["supporting_interfaces"] == "A::B;B::C"
