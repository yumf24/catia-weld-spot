"""Basic candidate filtering — Phase 2.

Drops candidates that fall outside their own region_bbox (defensive sanity
check -- always true given how points.layout_points constructs positions,
but matches PLAN.md's explicit rule and guards against future regressions)
and de-duplicates candidates from different face pairs that end up closer
than min_point_distance_mm to each other (points within a single region are
already spaced correctly by layout_points; this is for near-duplicates
across different mating-face pairs, e.g. one large plate split into several
smaller planar faces).

Normal-deviation and face-width filtering are enforced upstream, at pair/
region-construction time (see pairing.find_mating_pairs and
region.build_region) rather than here, since those checks decide whether a
region is valid in the first place.
"""

from __future__ import annotations

import numpy as np

from .config import WeldParams
from .schema import Candidate


def _within_region_bbox(candidate: Candidate, tol: float = 1e-6) -> bool:
    if candidate.region_bbox is None:
        return True
    pos = np.asarray(candidate.position)
    lo = np.asarray(candidate.region_bbox.min)
    hi = np.asarray(candidate.region_bbox.max)
    return bool(np.all(pos >= lo - tol) and np.all(pos <= hi + tol))


def filter_candidates(
    candidates: list[Candidate], params: WeldParams
) -> list[Candidate]:
    in_bbox = [c for c in candidates if _within_region_bbox(c)]

    kept: list[Candidate] = []
    kept_positions: list[np.ndarray] = []
    for c in in_bbox:
        pos = np.asarray(c.position)
        if any(
            np.linalg.norm(pos - kp) < params.min_point_distance_mm
            for kp in kept_positions
        ):
            continue
        kept.append(c)
        kept_positions.append(pos)

    return kept
