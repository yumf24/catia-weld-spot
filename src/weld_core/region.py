"""Candidate region construction — Phase 2.

Approximate the overlap of two mating faces by the intersection of their
projected 2D AABBs, on the plane midway between the two faces.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import WeldParams
from .geometry import (
    aabb_2d,
    aabb_overlap_2d,
    normal_angle_deg,
    normalize,
    point_to_plane_distance,
    project_to_plane,
)
from .schema import FaceRecord

Vec3 = tuple[float, float, float]


@dataclass
class Region:
    """A candidate weld region between two mating faces."""

    face_a_id: str
    face_b_id: str
    plane_origin: Vec3
    normal: Vec3
    bbox_min_2d: tuple[float, float]
    bbox_max_2d: tuple[float, float]
    gap_mm: float
    angle_deg: float


def build_region(face_a: FaceRecord, face_b: FaceRecord, params: WeldParams) -> Region | None:
    """Build the overlap region for a mating pair, or None if too narrow to weld.

    ``plane_origin`` sits midway between the two faces along ``normal``
    (face_a's normal) -- the "mid-thickness" position PLAN.md calls for when
    only the two mating faces themselves are known.
    """
    normal = normalize(face_a.normal)
    signed_gap = point_to_plane_distance(face_b.plane_origin, face_a.plane_origin, normal)
    mid_origin = tuple(float(c) for c in (normal * (signed_gap / 2.0) + face_a.plane_origin))

    pts_a = project_to_plane(face_a.vertices, mid_origin, normal)
    pts_b = project_to_plane(face_b.vertices, mid_origin, normal)
    min_a, max_a = aabb_2d(pts_a)
    min_b, max_b = aabb_2d(pts_b)
    overlap = aabb_overlap_2d(min_a, max_a, min_b, max_b)
    if overlap is None:
        return None

    lo, hi = overlap
    width, height = float(hi[0] - lo[0]), float(hi[1] - lo[1])
    if min(width, height) < params.min_face_width_mm:
        return None

    return Region(
        face_a_id=face_a.id,
        face_b_id=face_b.id,
        plane_origin=mid_origin,
        normal=(float(normal[0]), float(normal[1]), float(normal[2])),
        bbox_min_2d=(float(lo[0]), float(lo[1])),
        bbox_max_2d=(float(hi[0]), float(hi[1])),
        gap_mm=abs(float(signed_gap)),
        angle_deg=normal_angle_deg(face_a.normal, face_b.normal),
    )
