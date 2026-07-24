"""Safe candidate merging for exact planar interfaces."""

from __future__ import annotations

import numpy as np

from .config import WeldParams
from .schema import Candidate


def safe_merge_candidates(candidates: list[Candidate], params: WeldParams) -> tuple[list[Candidate], list[dict]]:
    """Merge only co-located duplicates from the *same* physical interface.

    Proximity alone is insufficient: neighbouring, independent interfaces may
    legitimately need separate weld points.  Before PW05 introduces explicit
    multi-interface connection groups, the canonical pair of supporting face
    IDs is the available physical-interface identity.
    """

    kept: list[Candidate] = []
    audit: list[dict] = []
    for candidate in candidates:
        interface = tuple(sorted(candidate.faces))
        position = np.asarray(candidate.position)
        match_index = next(
            (
                index for index, retained in enumerate(kept)
                if tuple(sorted(retained.faces)) == interface
                and np.linalg.norm(position - np.asarray(retained.position)) < params.min_point_distance_mm
            ),
            None,
        )
        if match_index is None:
            kept.append(candidate)
            audit.append({"candidate_id": candidate.id, "status": "retained", "interface": list(interface)})
            continue
        retained = kept[match_index]
        audit.append(
            {
                "candidate_id": candidate.id,
                "status": "merged",
                "into_candidate_id": retained.id,
                "interface": list(interface),
                "distance_mm": float(np.linalg.norm(position - np.asarray(retained.position))),
                "reason": "same_physical_interface_and_within_merge_distance",
            }
        )
    return kept, audit
