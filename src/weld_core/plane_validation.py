"""Compare extracted planar faces with a registered STEP surface reference.

The reference and source STEP exports can split the same physical plane into
different numbers of faces. Matching is therefore many-to-many: faces need
the same part name, a near-parallel normal, coincident supporting planes, and
overlapping projected vertex AABBs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .geometry import aabb_2d, normal_angle_deg, point_to_plane_distance, project_to_plane
from .schema import FacesDocument
from .step_geometry import StepFace

MAX_NORMAL_ANGLE_DEG = 0.1
MAX_PLANE_DISTANCE_MM = 0.02
_MIN_OVERLAP_AREA_MM2 = 1e-9


@dataclass(frozen=True)
class PlaneFace:
    """Geometry required to compare one planar face across independent exports."""

    id: str
    part: str
    normal: tuple[float, float, float]
    plane_origin: tuple[float, float, float]
    centroid: tuple[float, float, float]
    vertices: tuple[tuple[float, float, float], ...]
    residual_mm: float | None = None


def step_plane_faces(groups: dict[str, list[StepFace]]) -> list[PlaneFace]:
    """Convert parsed STEP faces to deterministic validation records."""
    out: list[PlaneFace] = []
    for part, faces in sorted(groups.items()):
        for index, face in enumerate(faces):
            if face.is_planar:
                out.append(
                    PlaneFace(
                        id=f"{part}/step_face_{index:04d}",
                        part=part,
                        normal=face.normal,
                        plane_origin=face.centroid,
                        centroid=face.centroid,
                        vertices=tuple(face.vertices),
                        residual_mm=face.max_residual,
                    )
                )
    return out


def document_plane_faces(doc: FacesDocument) -> list[PlaneFace]:
    """Convert CATIA/STEP-enriched ``faces.json`` data to validation records."""
    return [
        PlaneFace(
            id=face.id,
            part=face.part,
            normal=face.normal,
            plane_origin=face.plane_origin,
            centroid=face.centroid,
            vertices=tuple(face.vertices),
        )
        for face in doc.faces
        if face.surface_type == "planar"
    ]


def _overlap_area_mm2(source: PlaneFace, reference: PlaneFace) -> float:
    if len(source.vertices) < 3 or len(reference.vertices) < 3:
        return 0.0
    source_2d = project_to_plane(source.vertices, reference.plane_origin, reference.normal)
    reference_2d = project_to_plane(reference.vertices, reference.plane_origin, reference.normal)
    source_min, source_max = aabb_2d(source_2d)
    reference_min, reference_max = aabb_2d(reference_2d)
    lo = np.maximum(source_min, reference_min)
    hi = np.minimum(source_max, reference_max)
    size = hi - lo
    if np.any(size <= 0.0):
        return 0.0
    return float(size[0] * size[1])


def compare_faces(source: PlaneFace, reference: PlaneFace) -> dict[str, float] | None:
    """Return match metrics, or ``None`` when the two faces do not match."""
    if source.part != reference.part:
        return None
    angle = normal_angle_deg(source.normal, reference.normal)
    if angle > MAX_NORMAL_ANGLE_DEG:
        return None
    plane_distance = abs(
        point_to_plane_distance(reference.plane_origin, source.plane_origin, source.normal)
    )
    if plane_distance > MAX_PLANE_DISTANCE_MM:
        return None
    overlap_area = _overlap_area_mm2(source, reference)
    if overlap_area <= _MIN_OVERLAP_AREA_MM2:
        return None
    centroid_distance = float(
        np.linalg.norm(np.asarray(source.centroid) - np.asarray(reference.centroid))
    )
    return {
        "normal_angle_deg": angle,
        "plane_distance_mm": plane_distance,
        "aabb_overlap_area_mm2": overlap_area,
        "centroid_distance_mm": centroid_distance,
    }


def _face_record(face: PlaneFace) -> dict:
    return {
        "id": face.id,
        "part": face.part,
        "normal": list(face.normal),
        "plane_origin": list(face.plane_origin),
        "centroid": list(face.centroid),
        "vertex_count": len(face.vertices),
        "residual_mm": face.residual_mm,
    }


def validate_plane_faces(source_faces: Iterable[PlaneFace], reference_faces: Iterable[PlaneFace]) -> dict:
    """Perform a bidirectional, many-to-many plane-face validation."""
    sources = list(source_faces)
    references = list(reference_faces)
    source_matches: dict[str, list[dict]] = {face.id: [] for face in sources}
    reference_matches: dict[str, list[dict]] = {face.id: [] for face in references}

    for source in sources:
        for reference in references:
            metrics = compare_faces(source, reference)
            if metrics is not None:
                source_matches[source.id].append({"reference_id": reference.id, **metrics})
                reference_matches[reference.id].append({"source_id": source.id, **metrics})

    matched_sources = [face for face in sources if source_matches[face.id]]
    unmatched_sources = [face for face in sources if not source_matches[face.id]]
    matched_references = [face for face in references if reference_matches[face.id]]
    unmatched_references = [face for face in references if not reference_matches[face.id]]
    precision = len(matched_sources) / len(sources) if sources else 0.0
    recall = len(matched_references) / len(references) if references else 0.0
    return {
        "thresholds": {
            "normal_angle_deg": MAX_NORMAL_ANGLE_DEG,
            "plane_distance_mm": MAX_PLANE_DISTANCE_MM,
            "minimum_aabb_overlap_area_mm2": _MIN_OVERLAP_AREA_MM2,
        },
        "summary": {
            "algorithm_planar_faces": len(sources),
            "reference_planar_faces": len(references),
            "true_positives": len(matched_sources),
            "false_positives": len(unmatched_sources),
            "false_negatives": len(unmatched_references),
            "matched_reference_faces": len(matched_references),
            "precision": precision,
            "recall": recall,
            "passed": precision == 1.0 and recall == 1.0,
        },
        "algorithm_faces": [{**_face_record(face), "matches": source_matches[face.id]} for face in sources],
        "reference_faces": [{**_face_record(face), "matches": reference_matches[face.id]} for face in references],
        "false_positive_faces": [_face_record(face) for face in unmatched_sources],
        "false_negative_faces": [_face_record(face) for face in unmatched_references],
    }
