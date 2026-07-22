"""Schema + pipeline tests."""

import copy
import json
from pathlib import Path

import pytest

from weld_core.pipeline import main, run
from weld_core.schema import FacesDocument, dump_document, load_faces

FIXTURE = Path(__file__).parent / "fixtures" / "two_layer.json"


def test_load_two_layer_fixture():
    doc = load_faces(FIXTURE)
    assert doc.meta.part == "two_layer_sample"
    assert len(doc.faces) == 2
    assert doc.faces[0].surface_type == "planar"


def test_pipeline_runs_and_returns_document():
    doc = load_faces(FIXTURE)
    result = run(doc)
    assert result.meta.source == "two_layer_sample"
    assert "max_normal_angle_deg" in result.meta.params
    # The fixture's two faces overlap in a 90x45mm rectangle -> long axis
    # 90mm gets 3 evenly-spaced points at 45mm spacing (see test_points.py).
    assert len(result.candidates) == 3
    ids = [c.id for c in result.candidates]
    assert ids == ["wc_001", "wc_002", "wc_003"]
    for c in result.candidates:
        assert c.layer_type == "two_layer"
        assert c.spacing_mm == pytest.approx(45.0)
        assert c.position[2] == pytest.approx(1.025)
        assert set(c.faces) == {"PartA/Body1/face_top", "PartB/Body1/face_bottom"}


def _shifted_pair(doc: FacesDocument, dx: float, suffix: str) -> list:
    """A second, spatially-separated mating pair shaped like the fixture's."""
    faces = copy.deepcopy(doc.faces)
    for f in faces:
        f.id = f"{f.id}{suffix}"
        f.part = f"{f.part}{suffix}"
        f.plane_origin = (f.plane_origin[0] + dx, f.plane_origin[1], f.plane_origin[2])
        f.centroid = (f.centroid[0] + dx, f.centroid[1], f.centroid[2])
        f.vertices = [(v[0] + dx, v[1], v[2]) for v in f.vertices]
    return faces


def test_candidate_ids_stable_regardless_of_input_face_order():
    """wc_NNN ids must depend on candidate content, not on discovery order.

    catia/write_candidates.py matches points across CATIA sessions by id, so
    if two independent extractions of the same document yield the same faces
    in a different order (observed in practice, see DEVLOG.md), the same
    physical candidate must still land on the same id -- otherwise re-running
    the pipeline silently reassigns an existing point's position.
    """
    base = load_faces(FIXTURE)
    pair_2 = _shifted_pair(base, dx=1000.0, suffix="_2")

    forward = FacesDocument(meta=base.meta, faces=base.faces + pair_2)
    reversed_ = FacesDocument(meta=base.meta, faces=list(reversed(base.faces + pair_2)))

    result_forward = run(forward)
    result_reversed = run(reversed_)

    assert len(result_forward.candidates) == len(result_reversed.candidates) == 6

    forward_by_id = {c.id: c.position for c in result_forward.candidates}
    reversed_by_id = {c.id: c.position for c in result_reversed.candidates}
    assert forward_by_id == reversed_by_id


def test_cli_accepts_managed_faces_document_without_dataset_specific_provenance(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    faces_path = run_dir / "faces.json"
    dump_document(load_faces(FIXTURE), faces_path)
    (run_dir / "manifest.json").write_text(json.dumps({"part_id": "component-simplify", "run_id": "run", "artifacts": {"faces": {"path": "faces.json"}}}))
    output = run_dir / "candidates.json"
    assert main([str(faces_path), str(output)]) == 0
    result = load_faces(faces_path)
    candidates = json.loads(output.read_text(encoding="utf-8"))
    assert {face for candidate in candidates["candidates"] for face in candidate["faces"]} <= {face.id for face in result.faces}
    assert set(candidates["meta"]) == {"source", "core_version", "params"}
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["candidates"]["path"] == "candidates.json"
