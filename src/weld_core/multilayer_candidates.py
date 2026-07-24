"""Aggregate co-located exact-interface candidates into physical stacks."""

from __future__ import annotations

import numpy as np

from .config import WeldParams
from .schema import Candidate


def _parts(candidate: Candidate) -> set[str]:
    return {face.split("/", 1)[0] for face in candidate.faces if face}


def aggregate_multilayer_candidates(candidates: list[Candidate], params: WeldParams) -> tuple[list[Candidate], list[dict]]:
    """Aggregate only nearby interfaces that share a participating part.

    A shared part plus a co-located point represents a physical stack such as
    A--B and B--C.  Nearby A--B and C--D interfaces remain independent, which
    prevents an arbitrary global distance filter from erasing valid welds.
    """

    groups: list[list[Candidate]] = []
    for candidate in candidates:
        point = np.asarray(candidate.position)
        candidate_parts = _parts(candidate)
        for group in groups:
            if (
                candidate_parts & set().union(*(_parts(item) for item in group))
                and any(
                    np.linalg.norm(point - np.asarray(member.position)) <= params.coincident_merge_tolerance_mm
                    for member in group
                )
            ):
                group.append(candidate)
                break
        else:
            groups.append([candidate])

    aggregated: list[Candidate] = []
    audit: list[dict] = []
    for group in groups:
        representative = group[0]
        parts = set().union(*(_parts(item) for item in group))
        interfaces = sorted({interface for item in group for interface in item.supporting_interfaces})
        refs = sorted({ref for item in group for ref in item.exact_region_refs})
        tier = "low" if any(item.confidence_tier == "low" for item in group) else ("high" if refs else "medium")
        layer_count = max(2, len(parts))
        aggregated_candidate = representative.model_copy(update={
            "faces": sorted({face for item in group for face in item.faces}),
            "layer_type": "two_layer" if layer_count == 2 else "three_layer",
            "layer_count": layer_count,
            "supporting_interfaces": interfaces,
            "confidence_tier": tier,
            "exact_region_refs": refs,
        })
        aggregated.append(aggregated_candidate)
        audit.append({
            "representative_candidate_id": representative.id,
            "source_candidate_ids": [item.id for item in group],
            "position_mm": list(representative.position),
            "layer_count": layer_count,
            "supporting_interfaces": interfaces,
            "confidence_tier": tier,
            "status": "aggregated" if len(group) > 1 else "single_interface",
            "reason": "shared_part_and_coincident" if len(group) > 1 else "single_exact_interface_point",
        })
    return aggregated, audit
