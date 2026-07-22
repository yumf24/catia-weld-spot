"""Generic planar CAD-face selection by auditable geometry.

This module deliberately knows nothing about dataset names, templates,
reference STEP files, face indexes, or historical labels.  It accepts planar
faces with OCCT shapes and returns face/pair audit records based only on
parallelism, inter-plane gap, coarse spatial overlap and exact projected
CAD-boundary overlap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Trsf, gp_Vec

from .exact_face_overlap import CoplanarFacePair, ExactFaceOverlap, exact_face_overlap
from .geometry import (
    aabb_2d,
    aabb_overlap_2d,
    as_array,
    normal_angle_deg,
    point_to_plane_distance,
    project_to_plane,
)
from .step_geometry import StepFace

_ZERO_AREA_MM2 = 1e-9


@dataclass(frozen=True)
class GeneralSelectionParams:
    """Thresholds for generic planar face-pair selection."""

    max_normal_angle_deg: float = 0.5
    max_plane_gap_mm: float = 0.2
    min_overlap_area_mm2: float = 1.0
    min_face_coverage: float = 0.05
    min_effective_width_mm: float = 0.1
    allow_same_part_pairs: bool = False


@dataclass(frozen=True)
class GeneralPlaneFace:
    """Geometry needed to select a single planar CAD face."""

    id: str
    part: str
    normal: tuple[float, float, float]
    plane_origin: tuple[float, float, float]
    centroid: tuple[float, float, float]
    vertices: tuple[tuple[float, float, float], ...]
    shape: Any = field(compare=False, repr=False)


@dataclass(frozen=True)
class ExactPairMeasurement:
    """Exact projected overlap metrics for one pair of planar CAD faces."""

    normal_angle_deg: float
    plane_gap_mm: float
    common_area_mm2: float
    coverage_a: float
    coverage_b: float
    area_a_mm2: float
    area_b_mm2: float
    reason: str | None = None

    @property
    def matched(self) -> bool:
        return self.reason is None and self.common_area_mm2 > _ZERO_AREA_MM2


@dataclass(frozen=True)
class GeneralPairAudit:
    """Accepted or rejected generic pair with all decision measurements."""

    id: str
    face_a_id: str
    face_b_id: str
    part_a: str
    part_b: str
    accepted: bool
    reason: str | None
    normal_angle_deg: float | None = None
    plane_gap_mm: float | None = None
    aabb_overlap_width_mm: float | None = None
    aabb_overlap_height_mm: float | None = None
    common_area_mm2: float = 0.0
    coverage_a: float = 0.0
    coverage_b: float = 0.0
    score: float = 0.0


@dataclass(frozen=True)
class GeneralSelectionResult:
    """Deduplicated selected faces and the pair audits that support them."""

    selected_face_ids: tuple[str, ...]
    supporting_pair_ids_by_face: dict[str, tuple[str, ...]]
    pair_audits: tuple[GeneralPairAudit, ...]


def _reject(
    pair_id: str,
    face_a: GeneralPlaneFace,
    face_b: GeneralPlaneFace,
    reason: str,
    *,
    normal_angle_deg: float | None = None,
    plane_gap_mm: float | None = None,
    aabb_overlap_width_mm: float | None = None,
    aabb_overlap_height_mm: float | None = None,
) -> GeneralPairAudit:
    return GeneralPairAudit(
        id=pair_id,
        face_a_id=face_a.id,
        face_b_id=face_b.id,
        part_a=face_a.part,
        part_b=face_b.part,
        accepted=False,
        reason=reason,
        normal_angle_deg=normal_angle_deg,
        plane_gap_mm=plane_gap_mm,
        aabb_overlap_width_mm=aabb_overlap_width_mm,
        aabb_overlap_height_mm=aabb_overlap_height_mm,
    )


def _translated_shape(shape: Any, vector: np.ndarray) -> Any:
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(float(vector[0]), float(vector[1]), float(vector[2])))
    moved = BRepBuilderAPI_Transform(shape, transform, True)
    moved.Build()
    return moved.Shape()


def _project_shape_to_plane(face: GeneralPlaneFace, target: GeneralPlaneFace) -> Any:
    signed_gap = point_to_plane_distance(face.plane_origin, target.plane_origin, target.normal)
    translation = -signed_gap * as_array(target.normal) / np.linalg.norm(as_array(target.normal))
    return _translated_shape(face.shape, translation)


def exact_projected_pair_overlap(
    face_a: GeneralPlaneFace,
    face_b: GeneralPlaneFace,
    *,
    normal_angle_deg_value: float | None = None,
    plane_gap_mm_value: float | None = None,
) -> ExactPairMeasurement:
    """Measure exact overlap after projecting ``face_b`` to ``face_a``'s plane."""

    angle = normal_angle_deg_value
    if angle is None:
        angle = normal_angle_deg(face_a.normal, face_b.normal)
    signed_gap = point_to_plane_distance(face_b.plane_origin, face_a.plane_origin, face_a.normal)
    gap = abs(signed_gap) if plane_gap_mm_value is None else plane_gap_mm_value
    try:
        projected_b = _project_shape_to_plane(face_b, face_a)
        overlap: ExactFaceOverlap = exact_face_overlap(
            CoplanarFacePair(
                source=face_a.shape,
                reference=projected_b,
                normal_angle_deg=angle,
                plane_distance_mm=0.0,
            )
        )
    except Exception as exc:
        return ExactPairMeasurement(angle, gap, 0.0, 0.0, 0.0, 0.0, 0.0, f"projection_failed:{type(exc).__name__}")
    return ExactPairMeasurement(
        normal_angle_deg=angle,
        plane_gap_mm=gap,
        common_area_mm2=overlap.common_area_mm2,
        coverage_a=overlap.source_coverage,
        coverage_b=overlap.reference_coverage,
        area_a_mm2=overlap.source_area_mm2,
        area_b_mm2=overlap.reference_area_mm2,
        reason=overlap.reason,
    )


def _projected_aabb_overlap(face_a: GeneralPlaneFace, face_b: GeneralPlaneFace) -> tuple[float, float] | None:
    if len(face_a.vertices) < 3 or len(face_b.vertices) < 3:
        return None
    pts_a = project_to_plane(face_a.vertices, face_a.plane_origin, face_a.normal)
    pts_b = project_to_plane(face_b.vertices, face_a.plane_origin, face_a.normal)
    min_a, max_a = aabb_2d(pts_a)
    min_b, max_b = aabb_2d(pts_b)
    overlap = aabb_overlap_2d(min_a, max_a, min_b, max_b)
    if overlap is None:
        return None
    lo, hi = overlap
    width, height = hi - lo
    if width <= 0.0 or height <= 0.0:
        return None
    return float(width), float(height)


def evaluate_pair(
    face_a: GeneralPlaneFace,
    face_b: GeneralPlaneFace,
    params: GeneralSelectionParams = GeneralSelectionParams(),
) -> GeneralPairAudit:
    """Evaluate one face pair and return a complete accept/reject audit."""

    pair_id = f"{face_a.id}::{face_b.id}"
    if face_a.part == face_b.part and not params.allow_same_part_pairs:
        return _reject(pair_id, face_a, face_b, "same_part_excluded")

    angle = normal_angle_deg(face_a.normal, face_b.normal)
    if angle > params.max_normal_angle_deg:
        return _reject(pair_id, face_a, face_b, "normal_angle_exceeds_threshold", normal_angle_deg=angle)

    gap = abs(point_to_plane_distance(face_b.plane_origin, face_a.plane_origin, face_a.normal))
    if gap > params.max_plane_gap_mm:
        return _reject(pair_id, face_a, face_b, "plane_gap_exceeds_threshold", normal_angle_deg=angle, plane_gap_mm=gap)

    aabb_overlap = _projected_aabb_overlap(face_a, face_b)
    if aabb_overlap is None:
        return _reject(pair_id, face_a, face_b, "projected_aabb_no_overlap", normal_angle_deg=angle, plane_gap_mm=gap)
    overlap_width, overlap_height = aabb_overlap
    if min(overlap_width, overlap_height) < params.min_effective_width_mm:
        return _reject(
            pair_id,
            face_a,
            face_b,
            "effective_width_below_threshold",
            normal_angle_deg=angle,
            plane_gap_mm=gap,
            aabb_overlap_width_mm=overlap_width,
            aabb_overlap_height_mm=overlap_height,
        )

    measurement = exact_projected_pair_overlap(
        face_a,
        face_b,
        normal_angle_deg_value=angle,
        plane_gap_mm_value=gap,
    )
    reason = measurement.reason
    if measurement.common_area_mm2 < params.min_overlap_area_mm2:
        reason = reason or "overlap_area_below_threshold"
    elif min(measurement.coverage_a, measurement.coverage_b) < params.min_face_coverage:
        reason = "coverage_below_threshold"

    accepted = reason is None
    score = measurement.common_area_mm2 * min(measurement.coverage_a, measurement.coverage_b) if accepted else 0.0
    return GeneralPairAudit(
        id=pair_id,
        face_a_id=face_a.id,
        face_b_id=face_b.id,
        part_a=face_a.part,
        part_b=face_b.part,
        accepted=accepted,
        reason=reason,
        normal_angle_deg=measurement.normal_angle_deg,
        plane_gap_mm=measurement.plane_gap_mm,
        aabb_overlap_width_mm=overlap_width,
        aabb_overlap_height_mm=overlap_height,
        common_area_mm2=measurement.common_area_mm2,
        coverage_a=measurement.coverage_a,
        coverage_b=measurement.coverage_b,
        score=score,
    )


def select_general_planar_faces(
    faces: list[GeneralPlaneFace],
    params: GeneralSelectionParams = GeneralSelectionParams(),
) -> GeneralSelectionResult:
    """Evaluate all unordered pairs and deduplicate selected face ids."""

    audits: list[GeneralPairAudit] = []
    support: dict[str, list[str]] = {}
    ordered = sorted(faces, key=lambda face: face.id)
    for i, face_a in enumerate(ordered):
        for face_b in ordered[i + 1 :]:
            audit = evaluate_pair(face_a, face_b, params)
            audits.append(audit)
            if audit.accepted:
                support.setdefault(face_a.id, []).append(audit.id)
                support.setdefault(face_b.id, []).append(audit.id)

    return GeneralSelectionResult(
        selected_face_ids=tuple(sorted(support)),
        supporting_pair_ids_by_face={face_id: tuple(pair_ids) for face_id, pair_ids in sorted(support.items())},
        pair_audits=tuple(audits),
    )


def general_faces_from_step_groups(groups: dict[str, list[StepFace]]) -> list[GeneralPlaneFace]:
    """Convert parsed STEP faces to deterministic generic selection records."""

    faces: list[GeneralPlaneFace] = []
    for part, part_faces in sorted(groups.items()):
        for index, face in enumerate(part_faces):
            if not face.is_planar or face.shape is None:
                continue
            faces.append(
                GeneralPlaneFace(
                    id=f"{part}/step_face_{index:04d}",
                    part=part,
                    normal=face.normal,
                    plane_origin=face.centroid,
                    centroid=face.centroid,
                    vertices=tuple(face.vertices),
                    shape=face.shape,
                )
            )
    return faces
