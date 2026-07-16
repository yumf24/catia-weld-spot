"""Pure geometry helpers (numpy). CATIA-independent, fully testable.

Units are millimetres throughout, matching the CATIA extractor output.
"""

from __future__ import annotations

import math

import numpy as np

Vec3 = tuple[float, float, float]


def as_array(v) -> np.ndarray:
    return np.asarray(v, dtype=float)


def normalize(v) -> np.ndarray:
    a = as_array(v)
    n = np.linalg.norm(a)
    if n == 0.0:
        raise ValueError("cannot normalize a zero-length vector")
    return a / n


def normal_angle_deg(n1, n2) -> float:
    """Angle between two normals in degrees, ignoring sign/direction.

    Result is in [0, 90]: anti-parallel normals count as parallel, which is
    what we want for two plates facing each other.
    """
    a, b = normalize(n1), normalize(n2)
    dot = abs(float(np.clip(np.dot(a, b), -1.0, 1.0)))
    return math.degrees(math.acos(dot))


def point_to_plane_distance(point, plane_origin, plane_normal) -> float:
    """Signed distance from ``point`` to the plane, along the unit normal."""
    n = normalize(plane_normal)
    return float(np.dot(as_array(point) - as_array(plane_origin), n))


def gap_between_planes(origin_a, normal_a, origin_b) -> float:
    """Absolute distance between two (near-parallel) planes.

    Measured as the distance of B's origin to A's plane. For nearly parallel
    faces this approximates the plate gap.
    """
    return abs(point_to_plane_distance(origin_b, origin_a, normal_a))


def plane_basis(plane_normal) -> tuple[np.ndarray, np.ndarray]:
    """Build an orthonormal in-plane basis (u, v) for a plane with the given normal."""
    n = normalize(plane_normal)
    ref = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(n, ref))) > 0.9:
        ref = np.array([0.0, 1.0, 0.0])
    u = normalize(np.cross(n, ref))
    v = np.cross(n, u)
    return u, v


def project_to_plane(points, plane_origin, plane_normal) -> np.ndarray:
    """Project 3D points onto a plane, returning 2D coords in an in-plane basis.

    Returns an (N, 2) array of (u, v) coordinates.
    """
    u, v = plane_basis(plane_normal)
    pts = as_array(points).reshape(-1, 3) - as_array(plane_origin)
    return np.column_stack([pts @ u, pts @ v])


def unproject_from_plane(points_2d, plane_origin, plane_normal) -> np.ndarray:
    """Inverse of ``project_to_plane``: (u, v) plane coords -> 3D world points.

    Uses the same (u, v) basis convention as ``project_to_plane`` for the
    given normal, so a point round-tripped through project -> unproject
    returns to its original 3D location (up to its out-of-plane component).
    """
    u, v = plane_basis(plane_normal)
    pts = as_array(points_2d).reshape(-1, 2)
    return as_array(plane_origin) + pts[:, 0:1] * u + pts[:, 1:2] * v


def aabb_2d(points_2d) -> tuple[np.ndarray, np.ndarray]:
    """Axis-aligned bounding box of 2D points → (min[2], max[2])."""
    pts = as_array(points_2d).reshape(-1, 2)
    if pts.size == 0:
        raise ValueError("cannot compute AABB of empty point set")
    return pts.min(axis=0), pts.max(axis=0)


def aabb_overlap_2d(min_a, max_a, min_b, max_b):
    """Overlap rectangle of two 2D AABBs, or None if they do not overlap."""
    lo = np.maximum(as_array(min_a), as_array(min_b))
    hi = np.minimum(as_array(max_a), as_array(max_b))
    if np.any(lo > hi):
        return None
    return lo, hi


def fit_plane_residual(points) -> tuple[np.ndarray, np.ndarray, float]:
    """Least-squares plane fit via SVD → (unit normal, origin, max residual).

    ``origin`` is the point centroid; ``normal`` is the smallest right
    singular vector of the centered points; the residual is the largest
    absolute distance of any input point to that plane. With only 3 points
    the residual is always ~0 (three points are always coplanar) — callers
    that need to catch curved triangular faces should append an extra
    off-vertex sample point (e.g. a surface interior point) before calling
    this.
    """
    pts = as_array(points).reshape(-1, 3)
    if pts.shape[0] < 3:
        raise ValueError("need at least 3 points to fit a plane")
    origin = pts.mean(axis=0)
    centered = pts - origin
    _u, _s, vt = np.linalg.svd(centered, full_matrices=False)
    normal = vt[-1]
    normal = normal / np.linalg.norm(normal)
    residual = float(np.max(np.abs(centered @ normal)))
    return normal, origin, residual
