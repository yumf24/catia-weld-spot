"""Basic candidate filtering — Phase 2.

Drop points that are outside the overlap region, closer than
min_point_distance_mm to another point, on too-narrow overlaps, or whose
normal deviation exceeds the threshold.

TODO(Phase 2): implement `filter_candidates`.
"""

from __future__ import annotations

from .config import WeldParams
from .schema import Candidate


def filter_candidates(
    candidates: list[Candidate], params: WeldParams
) -> list[Candidate]:
    raise NotImplementedError("Phase 2: implement basic filtering")
