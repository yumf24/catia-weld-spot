"""Weld point layout — Phase 2.

Place points inside a candidate region: single point for regions under
min_spacing_mm, evenly spaced points (min..max spacing) along the long
direction otherwise. Z is set to the mid-thickness of the participating
plate stack.

TODO(Phase 2): implement `layout_points`.
"""

from __future__ import annotations

from .config import WeldParams
from .schema import Candidate


def layout_points(region, params: WeldParams) -> list[Candidate]:
    raise NotImplementedError("Phase 2: implement point layout")
