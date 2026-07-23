from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from weld_core.component_weld_ansa_scene import (
    LAYER_COLORS,
    LAYER_RGB,
    LINK_LAYER,
    MARKER_RADIUS_MM,
    SCENE_DATABASE,
    SCENE_DISPLAY_SCRIPT,
    SCENE_SCREENSHOTS,
    SCENE_STARTUP_SCRIPT,
    SPHERE_FACE_COUNT,
    load_scene_inputs,
    scene_paths,
)


def test_scene_inputs_accept_only_registered_primary_step(tmp_path):
    repo = tmp_path / "repo"
    raw = repo / "raw_data" / "component"
    raw.mkdir(parents=True)
    step = raw / "component.step"
    step.write_bytes(b"step")
    (raw / "manifest.json").write_text(json.dumps({"inputs": {"primary_model": {"path": "component.step", "sha256": hashlib.sha256(b"step").hexdigest()}}}), encoding="utf-8")
    run = tmp_path / "run"
    run.mkdir()
    (run / "manifest.json").write_text(json.dumps({"part_id": "component", "status": "completed"}), encoding="utf-8")
    (run / "weld_point_error_analysis.json").write_text(json.dumps({"true_positives": [], "false_positives": [], "false_negatives": []}), encoding="utf-8")

    inputs = load_scene_inputs(run, repo)

    assert inputs["cad_path"] == step
    assert inputs["marker_counts"][LINK_LAYER] == 0


def test_scene_paths_are_managed_under_run(tmp_path):
    paths = scene_paths(tmp_path)

    assert paths["database"] == tmp_path / SCENE_DATABASE
    assert paths["display_script"] == tmp_path / SCENE_DISPLAY_SCRIPT
    assert paths["startup_script"] == tmp_path / SCENE_STARTUP_SCRIPT
    assert set(path.name for name, path in paths.items() if name.startswith("screenshot_")) == {Path(value).name for value in SCENE_SCREENSHOTS.values()}
    assert {"isometric", "front", "right", "top"}.issubset(SCENE_SCREENSHOTS)
    assert SCENE_SCREENSHOTS["marker_detail"].endswith("component_weld_marker_detail.png")


def test_scene_marker_specification_has_colored_three_mm_spheres_and_hidden_links():
    assert MARKER_RADIUS_MM == 3.0
    assert SPHERE_FACE_COUNT == 6
    assert LAYER_COLORS == {
        "TP_TRUTH": "GREEN",
        "TP_CANDIDATE": "GREEN",
        "FP_CANDIDATE": "RED",
        "FN_TRUTH": "YELLOW",
    }
    assert LAYER_RGB["TP_TRUTH"] == LAYER_RGB["TP_CANDIDATE"]
    assert LINK_LAYER not in LAYER_COLORS


def test_review_startup_contract_applies_shaded_display_after_opening_database():
    root = Path(__file__).resolve().parents[1]
    builder = (root / "scripts" / "build_component_weld_ansa_scene.py").read_text(encoding="utf-8")
    launcher = (root / "scripts" / "open_component_weld_ansa_scene.py").read_text(encoding="utf-8")

    assert '"VIEWMODE": "PART"' in builder
    assert '"SHADOW": "on"' in builder
    for field in ("WIRE", "CONS", "Hot Points"):
        assert f'"{field}": "off"' in builder
    assert "base.Open(DATABASE_PATH)" in builder
    assert 'namespace["apply_review_display"]()' in builder
    assert 'f"load_script:{startup_script}"' in launcher
    assert 'group.add_argument(\n        "--ansa-part"' in launcher
    assert '"WIRE": "off"' in launcher
    assert '"CONS": "off"' in launcher


def test_explicit_ansa_part_startup_script_opens_requested_database_and_applies_display(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "scripts"))
    spec = importlib.util.spec_from_file_location("open_component_weld_ansa_scene", root / "scripts" / "open_component_weld_ansa_scene.py")
    assert spec and spec.loader
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)

    database = Path(r"D:\review\requested_part.ansa")
    source = launcher._custom_startup_script_source(database)

    assert repr(str(database)) in source
    assert "base.Open(DATABASE_PATH)" in source
    assert '"VIEWMODE": "PART"' in source
    assert '"WIRE": "off"' in source
    assert '"CONS": "off"' in source


def test_scene_inputs_reject_a_primary_step_hash_mismatch(tmp_path):
    repo = tmp_path / "repo"
    raw = repo / "raw_data" / "component"
    raw.mkdir(parents=True)
    (raw / "component.step").write_bytes(b"changed")
    (raw / "manifest.json").write_text(
        json.dumps({"inputs": {"primary_model": {"path": "component.step", "sha256": "not-the-file-hash"}}}),
        encoding="utf-8",
    )
    run = tmp_path / "run"
    run.mkdir()
    (run / "manifest.json").write_text(json.dumps({"part_id": "component", "status": "completed"}), encoding="utf-8")
    (run / "weld_point_error_analysis.json").write_text(
        json.dumps({"true_positives": [], "false_positives": [], "false_negatives": []}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="SHA-256"):
        load_scene_inputs(run, repo)
