"""Weld point layout — Phase 2.

Place points inside a candidate region: single point for regions under
min_spacing_mm (along the long axis), evenly spaced points (target
max_spacing_mm, never below min_spacing_mm) otherwise. Position is the
region's mid-plane (already mid-thickness, see region.build_region).
"""

from __future__ import annotations

import math

import numpy as np

from .config import WeldParams
from .geometry import unproject_from_plane
from .region import Region
from .schema import BBox, Candidate


def _corners_2d(region: Region) -> np.ndarray:
    (xmin, ymin), (xmax, ymax) = region.bbox_min_2d, region.bbox_max_2d
    return np.array([[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]])


def _region_bbox_3d(region: Region) -> BBox:
    corners_3d = unproject_from_plane(_corners_2d(region), region.plane_origin, region.normal)
    lo = corners_3d.min(axis=0)
    hi = corners_3d.max(axis=0)
    return BBox(
        min=(float(lo[0]), float(lo[1]), float(lo[2])),
        max=(float(hi[0]), float(hi[1]), float(hi[2])),
    )


def layout_points(region: Region, params: WeldParams) -> list[Candidate]:
    width = region.bbox_max_2d[0] - region.bbox_min_2d[0]
    height = region.bbox_max_2d[1] - region.bbox_min_2d[1]
    long_axis = 0 if width >= height else 1
    long_dim = max(width, height)

    center_2d = (
        (region.bbox_min_2d[0] + region.bbox_max_2d[0]) / 2.0,
        (region.bbox_min_2d[1] + region.bbox_max_2d[1]) / 2.0,
    )

    if long_dim < params.min_spacing_mm:
        points_2d = np.array([center_2d])
        spacing_mm = 0.0
    else:
        n_points = max(2, math.ceil(long_dim / params.max_spacing_mm) + 1)
        spacing_mm = long_dim / (n_points - 1)
        lo = region.bbox_min_2d[long_axis]
        hi = region.bbox_max_2d[long_axis]
        along = np.linspace(lo, hi, n_points)
        other = center_2d[1 - long_axis]
        points_2d = np.zeros((n_points, 2))
        points_2d[:, long_axis] = along
        points_2d[:, 1 - long_axis] = other

    positions_3d = unproject_from_plane(points_2d, region.plane_origin, region.normal)
    region_bbox = _region_bbox_3d(region)
    reason = (
        f"two-layer mating pair, gap={region.gap_mm:.3f}mm, "
        f"normal_angle={region.angle_deg:.2f}deg"
    )

    return [
        Candidate(
            id=f"{region.face_a_id}~{region.face_b_id}#{i}",
            position=(float(p[0]), float(p[1]), float(p[2])),
            faces=[region.face_a_id, region.face_b_id],
            layer_type="two_layer",
            spacing_mm=spacing_mm,
            region_bbox=region_bbox,
            reason=reason,
        )
        for i, p in enumerate(positions_3d)
    ]
