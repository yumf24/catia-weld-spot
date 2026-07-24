"""Tunable parameters for the weld-candidate pipeline.

Central place for all thresholds from PLAN.md so tuning is one edit.
"""

from __future__ import annotations

from pydantic import BaseModel


class WeldParams(BaseModel):
    # Pairing (candidate mating faces)
    max_normal_angle_deg: float = 5.0   # normals within this angle count as parallel
    max_gap_mm: float = 0.1             # face-to-face distance threshold

    # Point layout
    min_spacing_mm: float = 20.0        # below this, a region gets a single point
    max_spacing_mm: float = 70.0        # target upper bound between points
    coverage_radius_mm: float = 10.0    # exact 2-D layout coverage radius

    # Basic filtering
    min_point_distance_mm: float = 20.0  # drop points closer than this to another
    # Physical-station aggregation is deliberately much tighter than the
    # review/layout spacing above.  It must never erase valid 2-D coverage
    # points merely because they are near one another.
    coincident_merge_tolerance_mm: float = 0.05
    candidate_budget_target: int = 600
    min_face_width_mm: float = 5.0       # minimum overlap width to be weldable

    def as_dict(self) -> dict:
        return self.model_dump()
