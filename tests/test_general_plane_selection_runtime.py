from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.gp import gp_Pnt

from weld_core.general_plane_selection import GeneralSelectionParams, run_registered_general_plane_selection
from weld_core.schema import load_faces
from weld_core.step_geometry import StepFace


def _shape(x0: float, x1: float, y0: float = 0.0, y1: float = 10.0, z: float = 0.0):
    polygon = BRepBuilderAPI_MakePolygon()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        polygon.Add(gp_Pnt(x, y, z))
    polygon.Close()
    return BRepBuilderAPI_MakeFace(polygon.Wire()).Face()


def _step_face(
    part: str,
    *,
    x0: float = 0.0,
    x1: float = 10.0,
    z: float = 0.0,
    normal: tuple[float, float, float] = (0.0, 0.0, 1.0),
) -> StepFace:
    return StepFace(
        part_name=part,
        vertices=[(x0, 0.0, z), (x1, 0.0, z), (x1, 10.0, z), (x0, 10.0, z)],
        centroid=((x0 + x1) / 2.0, 5.0, z),
        normal=normal,
        area=(x1 - x0) * 10.0,
        is_planar=True,
        shape=_shape(x0, x1, z=z),
    )


def _raw_manifest(tmp_path: Path, part_id: str = "sample-part") -> tuple[Path, Path]:
    raw_root = tmp_path / "raw_data"
    part_dir = raw_root / part_id
    part_dir.mkdir(parents=True)
    primary = part_dir / "primary.step"
    reference = part_dir / "reference.step"
    primary.write_bytes(b"primary-step")
    reference.write_bytes(b"reference-step")
    (part_dir / "manifest.json").write_text(
        json.dumps(
            {
                "part_id": part_id,
                "inputs": {
                    "primary_model": {
                        "path": primary.name,
                        "sha256": hashlib.sha256(b"primary-step").hexdigest(),
                        "size_bytes": len(b"primary-step"),
                    },
                    "surface_reference": {
                        "path": reference.name,
                        "sha256": hashlib.sha256(b"reference-step").hexdigest(),
                        "size_bytes": len(b"reference-step"),
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return raw_root, primary


def test_registered_runtime_writes_stable_primary_only_managed_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    raw_root, primary = _raw_manifest(tmp_path)
    data_root = tmp_path / "data"
    parsed_paths: list[str] = []

    def fake_parse(path: str):
        parsed_paths.append(path)
        return {
            "PartB": [_step_face("PartB", x0=2.0, x1=12.0, z=0.05, normal=(0.0, 0.0, -1.0))],
            "PartA": [_step_face("PartA")],
            "PartC": [_step_face("PartC", x0=30.0, x1=40.0, z=0.05)],
        }

    monkeypatch.setattr("weld_core.step_geometry.parse_step_faces", fake_parse)

    run_dir = run_registered_general_plane_selection(
        "sample-part",
        run_label="generic",
        params=GeneralSelectionParams(min_overlap_area_mm2=1.0, min_face_coverage=0.1),
        raw_root=raw_root,
        data_root=data_root,
        now=datetime(2026, 7, 22, 16, 30, 0),
    )

    assert parsed_paths == [str(primary.resolve())]
    assert run_dir.name == "20260722-163000-generic"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert [record["role"] for record in manifest["raw_inputs"]] == ["primary_model"]
    assert set(manifest["artifacts"]) == {"faces.general-selected", "pair_audit", "selection_audit"}

    selected = load_faces(run_dir / "faces.general-selected.json")
    assert [face.id for face in selected.faces] == ["PartA/step_face_0000", "PartB/step_face_0000"]
    assert selected.meta.part == "sample-part"

    pair_audit = json.loads((run_dir / "pair_audit.json").read_text(encoding="utf-8"))
    accepted_pairs = [pair for pair in pair_audit["pairs"] if pair["accepted"]]
    assert [pair["id"] for pair in accepted_pairs] == ["PartA/step_face_0000::PartB/step_face_0000"]
    assert accepted_pairs[0]["gap_layer"] == "strict"

    selection_audit = json.loads((run_dir / "selection_audit.json").read_text(encoding="utf-8"))
    assert selection_audit["total_planar_faces"] == 3
    assert selection_audit["selected_face_count"] == 2
    assert selection_audit["source"]["role"] == "primary_model"
    assert selection_audit["selected_faces"][0]["supporting_pair_gap_layers"] == [
        {"pair_id": "PartA/step_face_0000::PartB/step_face_0000", "gap_layer": "strict"}
    ]
    assert [row["face_id"] for row in selection_audit["rejected_faces"]] == ["PartC/step_face_0000"]


def test_registered_runtime_is_deterministic_for_identical_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    raw_root, _ = _raw_manifest(tmp_path)
    data_root = tmp_path / "data"

    def fake_parse(_path: str):
        return {
            "PartB": [_step_face("PartB", x0=2.0, x1=12.0, z=0.05)],
            "PartA": [_step_face("PartA")],
        }

    monkeypatch.setattr("weld_core.step_geometry.parse_step_faces", fake_parse)

    first = run_registered_general_plane_selection("sample-part", raw_root=raw_root, data_root=data_root)
    second = run_registered_general_plane_selection("sample-part", raw_root=raw_root, data_root=data_root)

    assert (first / "faces.general-selected.json").read_text(encoding="utf-8") == (
        second / "faces.general-selected.json"
    ).read_text(encoding="utf-8")
    first_audit = json.loads((first / "pair_audit.json").read_text(encoding="utf-8"))
    second_audit = json.loads((second / "pair_audit.json").read_text(encoding="utf-8"))
    first_audit.pop("run_id")
    second_audit.pop("run_id")
    assert first_audit == second_audit
