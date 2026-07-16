"""Face pairing — Phase 2.

Find pairs of planar faces that may be welded: different parts, normals
near-parallel (<= max_normal_angle_deg, ignoring sign), face gap
<= max_gap_mm, and projected 2D AABBs overlap.
"""

from __future__ import annotations

import numpy as np

from .config import WeldParams
from .geometry import aabb_2d, aabb_overlap_2d, as_array, gap_between_planes, project_to_plane
from .schema import FaceRecord


def find_mating_pairs(
    faces: list[FaceRecord], params: WeldParams
) -> list[tuple[FaceRecord, FaceRecord]]:
    """Find candidate mating-face pairs among ``faces``.

    Callers should pre-filter ``faces`` to planar, non-manual_review faces
    with non-empty ``vertices`` (see ``pipeline.run``) -- this function
    assumes every face is eligible and only applies the pairing rules
    themselves.
    """
    n = len(faces)
    if n < 2:
        return []

    # Cheap, fully vectorized first pass: pairwise |cos(angle)| between every
    # pair of (unit) normals in one matrix multiply, instead of an O(n^2)
    # Python loop calling normal_angle_deg per pair -- at real-assembly scale
    # (~1900 eligible faces) the naive loop is noticeably slow, while this is
    # a single small matrix multiply.
    normals = np.array([as_array(f.normal) for f in faces])
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = normals / norms
    cos_matrix = np.clip(np.abs(normals @ normals.T), -1.0, 1.0)
    angle_matrix = np.degrees(np.arccos(cos_matrix))

    i_idx, j_idx = np.triu_indices(n, k=1)
    angle_ok = angle_matrix[i_idx, j_idx] <= params.max_normal_angle_deg

    pairs: list[tuple[FaceRecord, FaceRecord]] = []
    for i, j in zip(i_idx[angle_ok], j_idx[angle_ok]):
        face_a, face_b = faces[i], faces[j]
        if face_a.part == face_b.part:
            continue

        gap = gap_between_planes(face_a.plane_origin, face_a.normal, face_b.plane_origin)
        if gap > params.max_gap_mm:
            continue

        pts_a = project_to_plane(face_a.vertices, face_a.plane_origin, face_a.normal)
        pts_b = project_to_plane(face_b.vertices, face_a.plane_origin, face_a.normal)
        min_a, max_a = aabb_2d(pts_a)
        min_b, max_b = aabb_2d(pts_b)
        if aabb_overlap_2d(min_a, max_a, min_b, max_b) is None:
            continue

        pairs.append((face_a, face_b))

    return pairs
