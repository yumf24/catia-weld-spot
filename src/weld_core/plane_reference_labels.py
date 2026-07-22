"""Derive auditable single-CAD-face labels from a one-time STEP reference.

The reference STEP is intentionally accepted only by this template-building
stage.  Each reference planar face must resolve to exactly one primary STEP
face using part identity, supporting-plane tolerances, and exact CAD boundary
overlap -- never a projected AABB as an acceptance condition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .exact_face_overlap import (
    MAX_NORMAL_ANGLE_DEG,
    MAX_PLANE_DISTANCE_MM,
    CoplanarFacePair,
    exact_face_overlap,
)
from .geometry import normal_angle_deg, point_to_plane_distance
from .step_geometry import StepFace

MIN_SOURCE_COVERAGE = 0.95


@dataclass(frozen=True)
class IndexedStepFace:
    """A stable STEP traversal index paired with its parsed geometry."""

    part: str
    index: int
    face: StepFace

    @property
    def id(self) -> str:
        return f"{self.part}/step_face_{self.index:04d}"


def indexed_planar_faces(groups: dict[str, list[StepFace]]) -> list[IndexedStepFace]:
    """Return planar STEP faces in the parser's deterministic traversal order."""
    return [
        IndexedStepFace(part, index, face)
        for part, faces in sorted(groups.items())
        for index, face in enumerate(faces)
        if face.is_planar and face.shape is not None
    ]


def _candidate(source: IndexedStepFace, reference: IndexedStepFace) -> dict:
    angle = normal_angle_deg(source.face.normal, reference.face.normal)
    distance = abs(point_to_plane_distance(reference.face.centroid, source.face.centroid, source.face.normal))
    result = exact_face_overlap(CoplanarFacePair(source.face.shape, reference.face.shape, angle, distance))
    return {
        "source_face_id": source.id,
        "source_face_index": source.index,
        "normal_angle_deg": angle,
        "plane_distance_mm": distance,
        "common_area_mm2": result.common_area_mm2,
        "source_coverage": result.source_coverage,
        "reference_coverage": result.reference_coverage,
        "reason": result.reason,
        "accepted": result.matched and result.source_coverage >= MIN_SOURCE_COVERAGE,
    }


def build_reference_face_labels(
    source_faces: Iterable[IndexedStepFace], reference_faces: Iterable[IndexedStepFace]
) -> dict:
    """Build labels and complete audit data, raising no exception for bad labels.

    ``passed`` is false if a reference face has no unique accepted source face.
    The returned diagnostics preserve all geometrically plausible candidates so
    a failed one-time label build can be inspected rather than guessed.
    """
    sources = list(source_faces)
    references = list(reference_faces)
    audit: list[dict] = []
    labels: list[dict] = []
    for reference in references:
        candidates = [
            _candidate(source, reference)
            for source in sources
            if source.part == reference.part
        ]
        accepted = [candidate for candidate in candidates if candidate["accepted"]]
        record = {
            "reference_face_id": reference.id,
            "reference_face_index": reference.index,
            "part": reference.part,
            "candidates": candidates,
            "status": "rejected",
            "rejection_reason": None,
            "selected_source_face_id": None,
        }
        if len(accepted) == 1:
            chosen = accepted[0]
            record["status"] = "selected"
            record["selected_source_face_id"] = chosen["source_face_id"]
            labels.append({
                "part": reference.part,
                "source_face_id": chosen["source_face_id"],
                "source_face_index": chosen["source_face_index"],
                "reference_face_id": reference.id,
                "reference_face_index": reference.index,
                "common_area_mm2": chosen["common_area_mm2"],
                "source_coverage": chosen["source_coverage"],
                "reference_coverage": chosen["reference_coverage"],
                "normal_angle_deg": chosen["normal_angle_deg"],
                "plane_distance_mm": chosen["plane_distance_mm"],
            })
        elif not accepted:
            record["rejection_reason"] = "no_single_face_with_required_source_coverage"
        else:
            record["rejection_reason"] = "ambiguous_multiple_source_faces"
        audit.append(record)
    return {
        "thresholds": {
            "normal_angle_deg_max": MAX_NORMAL_ANGLE_DEG,
            "plane_distance_mm_max": MAX_PLANE_DISTANCE_MM,
            "source_coverage_min": MIN_SOURCE_COVERAGE,
        },
        "summary": {
            "source_planar_faces": len(sources),
            "reference_planar_faces": len(references),
            "selected_labels": len(labels),
            "rejected_reference_faces": sum(row["status"] != "selected" for row in audit),
            "passed": len(labels) == len(references),
        },
        "labels": labels,
        "reference_audit": audit,
    }
