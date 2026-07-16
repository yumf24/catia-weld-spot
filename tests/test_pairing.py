"""pairing.find_mating_pairs tests."""

from weld_core.config import WeldParams
from weld_core.pairing import find_mating_pairs
from weld_core.schema import FaceRecord

PARAMS = WeldParams()


def _face(id_, part, normal, plane_origin, vertices):
    return FaceRecord(
        id=id_,
        part=part,
        body="Body1",
        surface_type="planar",
        area=1.0,
        normal=normal,
        plane_origin=plane_origin,
        centroid=plane_origin,
        vertices=vertices,
        manual_review=False,
    )


SQUARE_A = [[0, 0, 1], [100, 0, 1], [100, 50, 1], [0, 50, 1]]
SQUARE_B_OVERLAP = [[10, 5, 1.05], [110, 5, 1.05], [110, 55, 1.05], [10, 55, 1.05]]
SQUARE_B_NO_OVERLAP = [[200, 200, 1.05], [300, 200, 1.05], [300, 250, 1.05], [200, 250, 1.05]]


def test_finds_mating_pair_for_close_parallel_overlapping_faces():
    a = _face("A/face_1", "PartA", [0, 0, 1], [0, 0, 1.0], SQUARE_A)
    b = _face("B/face_1", "PartB", [0, 0, -1], [0, 0, 1.05], SQUARE_B_OVERLAP)
    pairs = find_mating_pairs([a, b], PARAMS)
    assert len(pairs) == 1
    ids = {pairs[0][0].id, pairs[0][1].id}
    assert ids == {"A/face_1", "B/face_1"}


def test_same_part_does_not_pair():
    a = _face("A/face_1", "PartA", [0, 0, 1], [0, 0, 1.0], SQUARE_A)
    b = _face("A/face_2", "PartA", [0, 0, -1], [0, 0, 1.05], SQUARE_B_OVERLAP)
    assert find_mating_pairs([a, b], PARAMS) == []


def test_normal_angle_too_large_does_not_pair():
    a = _face("A/face_1", "PartA", [0, 0, 1], [0, 0, 1.0], SQUARE_A)
    b = _face("B/face_1", "PartB", [1, 0, 0], [0, 0, 1.05], SQUARE_B_OVERLAP)
    assert find_mating_pairs([a, b], PARAMS) == []


def test_gap_too_large_does_not_pair():
    a = _face("A/face_1", "PartA", [0, 0, 1], [0, 0, 1.0], SQUARE_A)
    far_vertices = [[x, y, 5.0] for x, y, _z in SQUARE_B_OVERLAP]
    b = _face("B/face_1", "PartB", [0, 0, -1], [0, 0, 5.0], far_vertices)
    assert find_mating_pairs([a, b], PARAMS) == []


def test_no_aabb_overlap_does_not_pair():
    a = _face("A/face_1", "PartA", [0, 0, 1], [0, 0, 1.0], SQUARE_A)
    b = _face("B/face_1", "PartB", [0, 0, -1], [0, 0, 1.05], SQUARE_B_NO_OVERLAP)
    assert find_mating_pairs([a, b], PARAMS) == []
