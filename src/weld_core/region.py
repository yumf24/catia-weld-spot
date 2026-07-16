"""Candidate region construction — Phase 2.

Approximate the overlap of two mating faces by the intersection of their
projected 2D AABBs; detect two-layer vs three-layer stacks.

TODO(Phase 2): implement `build_region` and layer detection.
"""

from __future__ import annotations

from .schema import FaceRecord


def build_region(face_a: FaceRecord, face_b: FaceRecord):
    raise NotImplementedError("Phase 2: implement projected-AABB overlap region")
