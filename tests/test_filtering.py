"""filtering.filter_candidates tests."""

from weld_core.config import WeldParams
from weld_core.filtering import filter_candidates
from weld_core.schema import BBox, Candidate

PARAMS = WeldParams()

BIG_BBOX = BBox(min=(-1000, -1000, -1000), max=(1000, 1000, 1000))


def _candidate(id_, position, region_bbox=BIG_BBOX):
    return Candidate(
        id=id_,
        position=position,
        faces=["A/face_1", "B/face_1"],
        layer_type="two_layer",
        spacing_mm=0.0,
        region_bbox=region_bbox,
        reason="test",
    )


def test_drops_candidate_too_close_to_another():
    a = _candidate("wc_1", (0.0, 0.0, 0.0))
    b = _candidate("wc_2", (5.0, 0.0, 0.0))  # 5mm away, under default 20mm
    kept = filter_candidates([a, b], PARAMS)
    assert [c.id for c in kept] == ["wc_1"]


def test_keeps_candidates_far_apart():
    a = _candidate("wc_1", (0.0, 0.0, 0.0))
    b = _candidate("wc_2", (100.0, 0.0, 0.0))
    kept = filter_candidates([a, b], PARAMS)
    assert {c.id for c in kept} == {"wc_1", "wc_2"}


def test_drops_candidate_outside_its_own_region_bbox():
    narrow_bbox = BBox(min=(-1.0, -1.0, -1.0), max=(1.0, 1.0, 1.0))
    inside = _candidate("wc_1", (0.0, 0.0, 0.0), region_bbox=narrow_bbox)
    outside = _candidate("wc_2", (500.0, 500.0, 500.0), region_bbox=narrow_bbox)
    kept = filter_candidates([inside, outside], PARAMS)
    assert [c.id for c in kept] == ["wc_1"]
