from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_ansa_weld_visualization.py"
SPEC = importlib.util.spec_from_file_location("check_ansa_weld_visualization", SCRIPT)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def test_expected_counts_requires_all_traceable_layers(tmp_path):
    manifest = {"required_ansa_version": "24.1.1", "layers": {name: {"count": 1} for name in CHECKER.EXPECTED_LAYERS}}
    (tmp_path / "ansa_import_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    assert CHECKER.expected_counts(tmp_path) == {name: 1 for name in CHECKER.EXPECTED_LAYERS}


def test_validation_rejects_missing_screenshot(tmp_path):
    database = tmp_path / "view.ansa"
    database.write_bytes(b"ansa")
    counts = {name: 1 for name in CHECKER.EXPECTED_LAYERS}
    result = {
        "pass": True,
        "process_exit_code": 0,
        "created_entity_counts": counts,
        "reopened_entity_counts": counts,
        "database_path": str(database),
        "screenshot_path": str(tmp_path / "missing.png"),
    }

    try:
        CHECKER._validate_result(tmp_path, result, counts)
    except ValueError as exc:
        assert "screenshot_path" in str(exc)
    else:
        raise AssertionError("expected missing screenshot to fail validation")
