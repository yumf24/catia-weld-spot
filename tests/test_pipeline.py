"""Schema + pipeline skeleton tests."""

from pathlib import Path

from weld_core.pipeline import run
from weld_core.schema import load_faces

FIXTURE = Path(__file__).parent / "fixtures" / "two_layer.json"


def test_load_two_layer_fixture():
    doc = load_faces(FIXTURE)
    assert doc.meta.part == "two_layer_sample"
    assert len(doc.faces) == 2
    assert doc.faces[0].surface_type == "planar"


def test_pipeline_runs_and_returns_document():
    doc = load_faces(FIXTURE)
    result = run(doc)
    # Phase 0 skeleton: produces a valid, empty candidates document.
    assert result.meta.source == "two_layer_sample"
    assert "max_normal_angle_deg" in result.meta.params
    assert isinstance(result.candidates, list)
