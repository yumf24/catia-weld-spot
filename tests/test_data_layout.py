from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from weld_core.data_layout import (
    DataLayoutError,
    create_run,
    find_run,
    register_artifact,
    register_managed_artifact,
    validate_identifier,
    verify_raw_inputs,
)


def _registered_raw(tmp_path: Path) -> tuple[Path, Path]:
    raw_root = tmp_path / "raw_data"
    source = raw_root / "sample" / "source.step"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"sample-cad")
    (source.parent / "manifest.json").write_text(
        json.dumps(
            {
                "part_id": "sample",
                "inputs": {
                    "primary_model": {
                        "path": "source.step",
                        "sha256": hashlib.sha256(b"sample-cad").hexdigest(),
                        "size_bytes": 10,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return raw_root, source


def test_identifier_rejects_path_traversal():
    assert validate_identifier("component-simplify") == "component-simplify"
    with pytest.raises(DataLayoutError):
        validate_identifier("../component")
    with pytest.raises(DataLayoutError):
        validate_identifier("Component")


def test_create_run_is_unique_and_registers_only_internal_artifacts(tmp_path: Path):
    raw_root, _ = _registered_raw(tmp_path)
    data_root = tmp_path / "data"
    now = datetime(2026, 7, 22, 14, 30, 15)
    first, manifest = create_run("sample", "full", now=now, raw_root=raw_root, data_root=data_root)
    second, _ = create_run("sample", "full", now=now, raw_root=raw_root, data_root=data_root)

    assert first.name == "20260722-143015-full"
    assert second.name == "20260722-143015-full-02"
    assert manifest["raw_inputs"][0]["role"] == "primary_model"
    artifact = first / "faces.json"
    artifact.write_text("{}", encoding="utf-8")
    register_artifact(first, "faces", artifact)
    evaluation = first / "evaluation.json"
    evaluation.write_text("{}", encoding="utf-8")
    assert register_managed_artifact(evaluation, "evaluation") is True
    assert register_managed_artifact(tmp_path / "outside.json", "outside") is False
    assert find_run("sample", root=data_root) == second
    with pytest.raises(DataLayoutError):
        register_artifact(first, "bad", tmp_path / "outside.json")


def test_verify_raw_inputs_detects_content_change(tmp_path: Path):
    raw_root, source = _registered_raw(tmp_path)
    assert verify_raw_inputs("sample", raw_root)[0]["size_bytes"] == 10
    source.write_bytes(b"changed")
    with pytest.raises(DataLayoutError, match="SHA-256"):
        verify_raw_inputs("sample", raw_root)
