from __future__ import annotations

from weld_core.plane_validation import PlaneFace, validate_plane_faces


def _plane(id_: str, *, part: str = "P", z: float = 0.0, normal=(0.0, 0.0, 1.0), x0=0.0, x1=10.0):
    return PlaneFace(
        id=id_, part=part, normal=normal, plane_origin=(0.0, 0.0, z),
        centroid=((x0 + x1) / 2.0, 5.0, z),
        vertices=((x0, 0.0, z), (x1, 0.0, z), (x1, 10.0, z), (x0, 10.0, z)),
    )


def test_opposite_normals_match():
    result = validate_plane_faces([_plane("source", normal=(0, 0, -1))], [_plane("reference")])
    assert result["summary"]["passed"] is True


def test_split_source_faces_can_match_one_reference():
    result = validate_plane_faces([_plane("left", x0=0, x1=5), _plane("right", x0=5, x1=10)], [_plane("reference")])
    assert result["summary"]["true_positives"] == 2
    assert result["summary"]["matched_reference_faces"] == 1
    assert result["summary"]["passed"] is True


def test_nonoverlapping_boundary_is_false_positive_and_negative():
    result = validate_plane_faces([_plane("source", x0=20, x1=30)], [_plane("reference")])
    assert result["summary"]["false_positives"] == 1
    assert result["summary"]["false_negatives"] == 1


def test_angle_and_plane_distance_thresholds_reject_face():
    angle = validate_plane_faces([_plane("angle", normal=(0.01, 0, 1))], [_plane("reference")])
    distance = validate_plane_faces([_plane("distance", z=0.03)], [_plane("reference")])
    assert angle["summary"]["passed"] is False
    assert distance["summary"]["passed"] is False
