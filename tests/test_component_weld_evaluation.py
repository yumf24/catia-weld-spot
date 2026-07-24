"""Contract tests for the isolated component weld candidate run."""

from __future__ import annotations

import json
from pathlib import Path

from weld_core.component_weld_evaluation import (
    COMPONENT_PART_ID,
    FROZEN_COMPONENT_WELD_PARAMS,
    create_component_candidate_run,
    planar_faces_document,
)
from weld_core.step_geometry import StepFace
from weld_core.component_weld_point_evaluation import evaluate_component_weld_points
from weld_core.component_weld_ansa import build_ansa_layers


def test_package_extracts_only_planar_faces(monkeypatch):
    monkeypatch.setattr(
        "weld_core.component_weld_evaluation.parse_step_faces",
        lambda _path: {
            "PartB": [StepFace("PartB", vertices=[(0, 0, 0), (1, 0, 0)], is_planar=True)],
            "PartA": [
                StepFace("PartA", vertices=[(0, 0, 0), (1, 0, 0), (0, 1, 0)], area=1.0, is_planar=True),
                StepFace("PartA", vertices=[(0, 0, 0), (1, 0, 0), (0, 1, 0)], is_planar=False),
            ],
        },
    )

    document = planar_faces_document(Path("primary.step"))

    assert document.meta.part == COMPONENT_PART_ID
    assert [face.id for face in document.faces] == ["PartA/STEP/face_00001"]
    assert document.faces[0].surface_type == "planar"


def test_package_creates_primary_only_completed_managed_run(monkeypatch, tmp_path):
    raw_root = tmp_path / "raw_data"
    part_dir = raw_root / COMPONENT_PART_ID
    part_dir.mkdir(parents=True)
    primary = part_dir / "component.step"
    primary.write_bytes(b"primary-step")
    from weld_core.data_layout import sha256_file

    (part_dir / "manifest.json").write_text(
        json.dumps({"part_id": COMPONENT_PART_ID, "inputs": {"primary_model": {"path": "component.step", "sha256": sha256_file(primary), "size_bytes": primary.stat().st_size}, "ground_truth_markers": {"path": "missing.step"}}}),
        encoding="utf-8",
    )
    run_dir = tmp_path / "data" / "component-weld-evaluation" / "fixture-candidate"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps({"status": "completed", "artifacts": {}}), encoding="utf-8")
    from weld_core.schema import dump_document
    dump_document(planar_faces_document_from_fixture(), run_dir / "faces.general-selected.json")
    (run_dir / "interface_region_audit.json").write_text(json.dumps({"regions": []}), encoding="utf-8")
    monkeypatch.setattr("weld_core.general_plane_selection.run_registered_general_plane_selection", lambda *args, **kwargs: run_dir)
    monkeypatch.setattr("weld_core.component_weld_evaluation.pipeline_main", lambda _argv: 0)

    actual_run_dir = create_component_candidate_run("candidate")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["status"] == "completed"
    assert actual_run_dir == run_dir
    assert run_dir.parent == tmp_path / "data" / "component-weld-evaluation"
    assert manifest["parameters"]["weld_params"] == FROZEN_COMPONENT_WELD_PARAMS.as_dict()
    assert (run_dir / "faces.general-selected.json").is_file()


def planar_faces_document_from_fixture():
    from weld_core.schema import FaceRecord, FacesDocument, FacesMeta

    return FacesDocument(
        meta=FacesMeta(part=COMPONENT_PART_ID),
        faces=[
            FaceRecord(id="A/STEP/face_0001", part="A", body="STEP", area=100.0, normal=(0, 0, 1), plane_origin=(0, 0, 0), centroid=(5, 5, 0), vertices=[(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]),
            FaceRecord(id="B/STEP/face_0001", part="B", body="STEP", area=100.0, normal=(0, 0, 1), plane_origin=(0, 0, 0.05), centroid=(5, 5, 0.05), vertices=[(0, 0, 0.05), (10, 0, 0.05), (10, 10, 0.05), (0, 10, 0.05)]),
        ],
    )


def test_point_evaluation_publishes_traceable_counts_and_sensitivity():
    from weld_core.schema import Candidate, CandidatesDocument, GroundTruthDocument, GroundTruthPoint

    truth = GroundTruthDocument(points=[GroundTruthPoint(id="gt-1", position=(0, 0, 0)), GroundTruthPoint(id="gt-2", position=(100, 0, 0))])
    candidates = CandidatesDocument(candidates=[Candidate(id="wc-1", position=(3, 0, 0), faces=["face-a"]), Candidate(id="wc-2", position=(200, 0, 0), faces=["face-b"])])

    report, analysis = evaluate_component_weld_points(truth, candidates)

    assert report["summary"]["true_positives"] == len(analysis["true_positives"]) == 1
    assert report["summary"]["false_positives"] == len(analysis["false_positives"]) == 1
    assert report["summary"]["false_negatives"] == len(analysis["false_negatives"]) == 1
    assert report["summary"]["f1"] == 0.5
    assert set(report["sensitivity_by_tolerance_mm"]) == {"5.0", "10.0", "20.0"}
    assert analysis["true_positives"][0]["candidate_faces"] == ["face-a"]


def test_point_evaluation_adds_planar_supported_denominator_and_fn_attribution():
    from weld_core.component_weld_point_evaluation import enrich_with_planar_adjudication
    from weld_core.schema import Candidate, CandidatesDocument, GroundTruthDocument, GroundTruthPoint
    truth = GroundTruthDocument(points=[GroundTruthPoint(id="supported", position=(0, 0, 0)), GroundTruthPoint(id="unresolved", position=(100, 0, 0))])
    candidates = CandidatesDocument(candidates=[Candidate(id="wc", position=(40, 0, 0), faces=["a", "b"], confidence_tier="high")])
    report, analysis = evaluate_component_weld_points(truth, candidates)
    enrich_with_planar_adjudication(report, analysis, {"points": [
        {"ground_truth_id": "supported", "position_mm": [0, 0, 0], "status": "planar_supported"},
        {"ground_truth_id": "unresolved", "position_mm": [100, 0, 0], "status": "out_of_scope_or_unresolved"},
    ]}, candidates, interface_audit={"regions": [{
        "id": "a::b", "plane_gap_mm": 0.5, "common_area_mm2": 125.0,
    }]})
    assert report["planar_supported_summary"]["ground_truth_count"] == 1
    assert report["candidate_stratification"]["confidence_tier"] == {"high": 1}
    assert analysis["false_negative_attribution_counts"]["region_not_covered"] == 1
    assert report["false_positive_stratification"]["rows"] == [{
        "candidate_id": "wc", "confidence_tier": "high", "layer_count": 2,
        "interface_id": None, "plane_gap_mm": None, "common_area_mm2": None,
    }]


def test_point_evaluation_stratifies_false_positives_by_interface_geometry():
    from weld_core.component_weld_point_evaluation import enrich_with_planar_adjudication
    from weld_core.schema import Candidate, CandidatesDocument, GroundTruthDocument, GroundTruthPoint

    truth = GroundTruthDocument(points=[GroundTruthPoint(id="supported", position=(0, 0, 0))])
    candidates = CandidatesDocument(candidates=[Candidate(
        id="extra", position=(100, 0, 0), faces=["a", "b"], layer_count=3,
        confidence_tier="low", supporting_interfaces=["a::b"],
    )])
    report, analysis = evaluate_component_weld_points(truth, candidates)
    enrich_with_planar_adjudication(report, analysis, {"points": [{
        "ground_truth_id": "supported", "position_mm": [0, 0, 0], "status": "planar_supported",
    }]}, candidates, interface_audit={"regions": [{
        "id": "a::b", "plane_gap_mm": 0.4, "common_area_mm2": 42.0,
    }]})

    assert analysis["false_positives"][0]["interface_geometry"] == [{
        "interface_id": "a::b", "plane_gap_mm": 0.4, "common_area_mm2": 42.0,
    }]
    assert report["false_positive_stratification"]["rows"] == [{
        "candidate_id": "extra", "confidence_tier": "low", "layer_count": 3,
        "interface_id": "a::b", "plane_gap_mm": 0.4, "common_area_mm2": 42.0,
    }]


def test_point_evaluation_attributes_audited_budget_exclusion():
    from weld_core.component_weld_point_evaluation import enrich_with_planar_adjudication
    from weld_core.schema import Candidate, CandidatesDocument, GroundTruthDocument, GroundTruthPoint

    truth = GroundTruthDocument(points=[GroundTruthPoint(id="supported", position=(0, 0, 0))])
    candidates = CandidatesDocument(candidates=[Candidate(id="far", position=(100, 0, 0), faces=["a", "b"])])
    report, analysis = evaluate_component_weld_points(truth, candidates)
    enrich_with_planar_adjudication(report, analysis, {"points": [{
        "ground_truth_id": "supported", "position_mm": [0, 0, 0], "status": "planar_supported",
        "supporting_interfaces": ["a::b"],
    }]}, candidates, {"original_exact_layout_points": [{
        "position_mm": [0, 0, 0], "source_interfaces": ["a::b"],
    }], "final_candidates": [{"position_mm": [0, 0, 0], "status": "budget_excluded"}]})
    assert analysis["false_negatives"][0]["attribution"] == "budget_excluded"
    assert analysis["false_negative_attribution_counts"]["budget_excluded"] == 1


def test_point_evaluation_accepts_structured_adjudication_interface_evidence():
    from weld_core.component_weld_point_evaluation import enrich_with_planar_adjudication
    from weld_core.schema import Candidate, CandidatesDocument, GroundTruthDocument, GroundTruthPoint

    truth = GroundTruthDocument(points=[GroundTruthPoint(id="supported", position=(0, 0, 0))])
    candidates = CandidatesDocument(candidates=[Candidate(id="far", position=(100, 0, 0), faces=["a", "b"])])
    report, analysis = evaluate_component_weld_points(truth, candidates)
    enrich_with_planar_adjudication(report, analysis, {"points": [{
        "ground_truth_id": "supported", "position_mm": [0, 0, 0], "status": "planar_supported",
        "supporting_interfaces": [{"face_a_id": "a", "face_b_id": "b"}],
    }]}, candidates, {"original_exact_layout_points": []})

    assert analysis["false_negatives"][0]["attribution"] == "interface_not_found"


def test_ansa_layers_keep_error_analysis_source_ids():
    layers = build_ansa_layers({
        "true_positives": [{"ground_truth_id": "gt-1", "ground_truth_position_mm": [0, 0, 0], "candidate_id": "wc-1", "candidate_position_mm": [1, 0, 0], "candidate_faces": ["f-1"]}],
        "false_positives": [{"candidate_id": "wc-2", "candidate_position_mm": [2, 0, 0], "candidate_faces": ["f-2"]}],
        "false_negatives": [{"ground_truth_id": "gt-2", "ground_truth_position_mm": [3, 0, 0]}],
    })
    assert layers["TP_TRUTH"][0]["source_id"] == "gt-1"
    assert layers["TP_CANDIDATE"][0]["faces"] == "f-1"
    assert layers["MATCH_LINK"][0]["source_id"] == "gt-1->wc-1"
    assert len(layers["FP_CANDIDATE"]) == len(layers["FN_TRUTH"]) == 1
