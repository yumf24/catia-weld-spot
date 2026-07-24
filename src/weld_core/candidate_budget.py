"""Deterministic, geometry-only interface-balanced candidate budgeting."""

from __future__ import annotations

import numpy as np

from .config import WeldParams
from .schema import Candidate


def _key(candidate: Candidate) -> tuple:
    return (tuple(sorted(candidate.supporting_interfaces)), tuple(candidate.position), candidate.id)


def _distance(left: Candidate, right: Candidate) -> float:
    return float(np.linalg.norm(np.asarray(left.position) - np.asarray(right.position)))


def select_interface_balanced_candidates(
    candidates: list[Candidate], params: WeldParams
) -> tuple[list[Candidate], dict]:
    """Select a bounded, reproducible subset without reading evaluation data.

    Every interface receives one deterministic seed while capacity permits.
    Remaining places are assigned to the least represented interface, using a
    farthest-point choice within that interface.  A multi-interface physical
    station counts for every interface it supports.
    """
    ordered = sorted(candidates, key=_key)
    target = params.candidate_budget_target
    by_interface: dict[str, list[Candidate]] = {}
    for candidate in ordered:
        for interface in candidate.supporting_interfaces:
            by_interface.setdefault(interface, []).append(candidate)
    selected: list[Candidate] = []
    selected_ids: set[str] = set()
    selection_reason: dict[str, str] = {}

    def choose(candidate: Candidate, reason: str) -> None:
        if candidate.id not in selected_ids and len(selected) < target:
            selected.append(candidate)
            selected_ids.add(candidate.id)
            selection_reason[candidate.id] = reason

    for interface in sorted(by_interface):
        choose(by_interface[interface][0], "interface_seed")

    while len(selected) < min(target, len(ordered)):
        counts = {
            interface: sum(interface in item.supporting_interfaces for item in selected)
            for interface in by_interface
        }
        candidates_by_priority = []
        for interface in sorted(by_interface, key=lambda item: (counts[item], item)):
            available = [item for item in by_interface[interface] if item.id not in selected_ids]
            if not available:
                continue
            represented = [item for item in selected if interface in item.supporting_interfaces]
            ranked = sorted(
                available,
                key=lambda item: (
                    -min((_distance(item, prior) for prior in represented), default=float("inf")),
                    _key(item),
                ),
            )
            candidates_by_priority.append((counts[interface], interface, ranked[0]))
        if not candidates_by_priority:
            break
        _, interface, candidate = min(candidates_by_priority, key=lambda row: (row[0], row[1], _key(row[2])))
        choose(candidate, f"least_represented_interface_farthest_point:{interface}")

    selected.sort(key=_key)
    audit_rows = []
    for candidate in ordered:
        selected_here = candidate.id in selected_ids
        audit_rows.append({
            "source_candidate_id": candidate.id,
            "position_mm": list(candidate.position),
            "supporting_interfaces": candidate.supporting_interfaces,
            "status": "selected" if selected_here else "budget_excluded",
            "reason": selection_reason.get(candidate.id, "candidate_budget_target_reached"),
        })
    return selected, {
        "format_version": 1,
        "parameters": {"candidate_budget_target": target},
        "candidate_pool_count": len(ordered),
        "selected_count": len(selected),
        "interface_count": len(by_interface),
        "stations": audit_rows,
    }
