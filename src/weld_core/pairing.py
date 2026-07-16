"""Face pairing — Phase 2.

Find pairs of planar faces that may be welded: normals near-parallel
(<= max_normal_angle_deg, ignoring sign), face gap <= max_gap_mm, and
projected 2D AABBs overlap.

TODO(Phase 2): implement `find_mating_pairs`.
"""

from __future__ import annotations

from .config import WeldParams
from .schema import FaceRecord


def find_mating_pairs(
    faces: list[FaceRecord], params: WeldParams
) -> list[tuple[FaceRecord, FaceRecord]]:
    raise NotImplementedError("Phase 2: implement mating-face pairing")
