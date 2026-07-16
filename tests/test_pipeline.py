"""Schema + pipeline tests."""

from pathlib import Path

import pytest

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
