from __future__ import annotations

import json
from pathlib import Path

import pytest

from weld_core.data_layout import create_run, sha256_file
from weld_core.pipeline import main as pipeline_main
from weld_core.production_truth_isolation import (
    ProductionTruthIsolationError,
    assert_production_read_path,
)
from weld_core.schema import FaceRecord, FacesDocument, dump_document


@pytest.mark.parametrize(
    "filename",
    [
        "SPOT.step",
        "ground_truth.json",
        "planar_truth_adjudication.json",
        "operating_frontier.json",
        "weld_point_error_analysis.json",
    ],
)
def test_production_guard_rejects_every_evaluation_only_filename(filename):
    with pytest.raises(ProductionTruthIsolationError, match="evaluation-only"):
        assert_production_read_path(filename)


def test_pipeline_rejects_evaluation_only_input_before_it_attempts_to_parse_it(tmp_path, capsys):
    faces = FacesDocument(faces=[FaceRecord(id="face", part="A", body="B")])
    forbidden_input = tmp_path / "SPOT.step"
    dump_document(faces, forbidden_input)

    assert pipeline_main([str(forbidden_input), str(tmp_path / "candidates.json")]) == 1
    assert "evaluation-only" in capsys.readouterr().err


def test_production_run_registration_hashes_only_the_primary_model(tmp_path):
    raw_root = tmp_path / "raw_data"
    part_dir = raw_root / "component"
    part_dir.mkdir(parents=True)
    primary = part_dir / "component.step"
    truth = part_dir / "SPOT.step"
    primary.write_bytes(b"primary")
    truth.write_bytes(b"truth")
    (part_dir / "manifest.json").write_text(json.dumps({
        "part_id": "component",
        "inputs": {
            "primary_model": {"path": "component.step", "sha256": sha256_file(primary)},
            "ground_truth_markers": {"path": "SPOT.step", "sha256": sha256_file(truth)},
        },
    }), encoding="utf-8")

    run_dir, manifest = create_run(
        "component", "primary-only", raw_root=raw_root, data_root=tmp_path / "data",
        input_roles=["primary_model"],
    )

    assert run_dir.is_dir()
    assert [row["role"] for row in manifest["raw_inputs"]] == ["primary_model"]
    assert manifest["raw_inputs"][0]["path"].endswith("component.step")


def test_full_production_entrypoint_declares_the_primary_input_role_only():
    source = (Path(__file__).resolve().parent.parent / "scripts" / "run_full_pipeline.py").read_text(encoding="utf-8")
    assert 'input_roles=["primary_model"]' in source
