"""Evaluation-only adjudication of weld-point support by planar CAD interfaces.

This module is intentionally separate from the candidate pipeline.  It reads
ground truth only when an offline evaluation command calls it, and records an
explicit unresolved result whenever OCCT cannot establish the required
geometry rather than inferring support from a bounding box.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import combinations
from typing import Any, Callable, Iterable

import numpy as np

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex, BRepBuilderAPI_Transform
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.gp import gp_Pnt, gp_Trsf, gp_Vec

from .exact_face_overlap import _BOOLEAN_FUZZY_TOL_MM, surface_area_mm2
from .general_plane_selection import GeneralPlaneFace, _projected_aabb_overlap
from .geometry import aabb_2d, as_array, normal_angle_deg, point_to_plane_distance, project_to_plane


@dataclass(frozen=True)
class PlanarTruthParams:
    max_normal_angle_deg: float = 0.5
    max_plane_gap_mm: float = 1.5
    min_common_area_mm2: float = 1.0
    point_region_tolerance_mm: float = 0.05


@dataclass(frozen=True)
class InterfaceEvidence:
    """One exact, point-specific interface assessment."""

    face_a_id: str
    face_b_id: str
    part_a: str
    part_b: str
    normal_angle_deg: float
    plane_gap_mm: float
    common_area_mm2: float = 0.0
    point_relation: str = "unresolved"
    reason: str | None = None
    layer_count: int = 2

    @property
    def supports_point(self) -> bool:
        return self.reason is None and self.common_area_mm2 > 0.0 and self.point_relation == "inside_exact_common_region"


InterfaceBuilder = Callable[[GeneralPlaneFace, GeneralPlaneFace, tuple[float, float, float], PlanarTruthParams], InterfaceEvidence]


def _point_in_projected_aabb(point: tuple[float, float, float], face: GeneralPlaneFace, target: GeneralPlaneFace) -> bool:
    if len(face.vertices) < 3:
        return False
    face_min, face_max = aabb_2d(project_to_plane(face.vertices, target.plane_origin, target.normal))
    projected_point = project_to_plane([point], target.plane_origin, target.normal)[0]
    return bool(np.all(projected_point >= face_min) and np.all(projected_point <= face_max))


def _translated_to_plane(shape: Any, source_origin: tuple[float, float, float], target: GeneralPlaneFace) -> Any:
    signed_gap = point_to_plane_distance(source_origin, target.plane_origin, target.normal)
    unit_normal = as_array(target.normal) / np.linalg.norm(as_array(target.normal))
    transform = gp_Trsf()
    delta = -signed_gap * unit_normal
    transform.SetTranslation(gp_Vec(float(delta[0]), float(delta[1]), float(delta[2])))
    moved = BRepBuilderAPI_Transform(shape, transform, True)
    moved.Build()
    return moved.Shape()


def exact_interface_evidence(
    face_a: GeneralPlaneFace,
    face_b: GeneralPlaneFace,
    point: tuple[float, float, float],
    params: PlanarTruthParams,
) -> InterfaceEvidence:
    """Use OCCT's projected common face and a point-to-region distance test."""
    angle = normal_angle_deg(face_a.normal, face_b.normal)
    gap = abs(point_to_plane_distance(face_b.plane_origin, face_a.plane_origin, face_a.normal))
    common_area = 0.0
    try:
        projected_b = _translated_to_plane(face_b.shape, face_b.plane_origin, face_a)
        operation = BRepAlgoAPI_Common(face_a.shape, projected_b)
        operation.SetFuzzyValue(_BOOLEAN_FUZZY_TOL_MM)
        operation.Build()
        common = operation.Shape()
        common_area = surface_area_mm2(common)
        if common_area <= params.min_common_area_mm2:
            return InterfaceEvidence(face_a.id, face_b.id, face_a.part, face_b.part, angle, gap, common_area, "outside_exact_common_region", "common_area_below_threshold")

        normal = as_array(face_a.normal) / np.linalg.norm(as_array(face_a.normal))
        signed = point_to_plane_distance(point, face_a.plane_origin, normal)
        projected_point = as_array(point) - signed * normal
        vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*map(float, projected_point))).Vertex()
        distance = BRepExtrema_DistShapeShape(common, vertex)
        distance.Perform()
        value = float(distance.Value()) if distance.IsDone() else float("inf")
        relation = "inside_exact_common_region" if value <= params.point_region_tolerance_mm else "outside_exact_common_region"
        return InterfaceEvidence(face_a.id, face_b.id, face_a.part, face_b.part, angle, gap, common_area, relation)
    except Exception as exc:
        return InterfaceEvidence(face_a.id, face_b.id, face_a.part, face_b.part, angle, gap, common_area, "unresolved", f"occt_exception:{type(exc).__name__}")


def adjudicate_planar_truth(
    points: Iterable[Any],
    faces: Iterable[GeneralPlaneFace],
    params: PlanarTruthParams = PlanarTruthParams(),
    interface_builder: InterfaceBuilder = exact_interface_evidence,
) -> dict[str, Any]:
    """Return one conservative, auditable status for every supplied truth point."""
    ordered_faces = sorted(faces, key=lambda item: item.id)
    records: list[dict[str, Any]] = []
    for point in points:
        position = tuple(float(value) for value in point.position)
        # A point in a two-face interface is at most one inter-plane gap away
        # from each supporting plane.  This inexpensive per-point filter keeps
        # the offline CAD run practical without using an AABB as acceptance.
        nearby_faces = [
            face
            for face in ordered_faces
            if abs(point_to_plane_distance(position, face.plane_origin, face.normal)) <= params.max_plane_gap_mm
        ]
        evidence: list[InterfaceEvidence] = []
        qualified_pair_seen = False
        for face_a, face_b in combinations(nearby_faces, 2):
            if face_a.part == face_b.part:
                continue
            angle = normal_angle_deg(face_a.normal, face_b.normal)
            if angle > params.max_normal_angle_deg:
                continue
            gap = abs(point_to_plane_distance(face_b.plane_origin, face_a.plane_origin, face_a.normal))
            if gap > params.max_plane_gap_mm:
                continue
            # A projected AABB can safely reject a pair that cannot share any
            # region.  It is never used to accept a pair: exact OCCT evidence
            # below remains mandatory.
            if _projected_aabb_overlap(face_a, face_b) is None:
                continue
            if not _point_in_projected_aabb(position, face_a, face_a) or not _point_in_projected_aabb(position, face_b, face_a):
                continue
            qualified_pair_seen = True
            evidence.append(interface_builder(face_a, face_b, position, params))

        feasible = [item for item in evidence if item.supports_point]
        if len(feasible) == 1:
            status, reason = "planar_supported", None
        elif len(feasible) > 1:
            status, reason = "out_of_scope_or_unresolved", "ambiguous_multiple_feasible_interfaces"
        elif any(item.point_relation == "unresolved" for item in evidence):
            status, reason = "out_of_scope_or_unresolved", "insufficient_exact_geometry_evidence"
        elif qualified_pair_seen:
            status, reason = "out_of_scope_or_unresolved", "outside_exact_common_region"
        else:
            status, reason = "out_of_scope_or_unresolved", "no_qualifying_planar_interface"

        records.append(
            {
                "ground_truth_id": point.id,
                "position_mm": list(position),
                "status": status,
                "reason": reason,
                "supporting_interfaces": [asdict(item) for item in feasible],
                "evaluated_interfaces": [asdict(item) for item in evidence],
                "layer_count": feasible[0].layer_count if len(feasible) == 1 else None,
            }
        )

    supported = sum(record["status"] == "planar_supported" for record in records)
    return {
        "format_version": 1,
        "scope": "evaluation_only_planar_truth_adjudication",
        "production_behavior_changed": False,
        "parameters": asdict(params),
        "summary": {
            "ground_truth_count": len(records),
            "planar_supported_count": supported,
            "out_of_scope_or_unresolved_count": len(records) - supported,
        },
        "points": records,
    }


def adjudication_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Planar truth adjudication",
        "",
        "This is evaluation-only evidence. Candidate generation does not read this report or ground truth.",
        "",
        f"- Ground-truth points: {summary['ground_truth_count']}",
        f"- Planar supported: {summary['planar_supported_count']}",
        f"- Out of scope or unresolved: {summary['out_of_scope_or_unresolved_count']}",
        "",
        "| Truth ID | Status | Reason | Interfaces |",
        "|---|---|---|---|",
    ]
    for point in report["points"]:
        interfaces = ", ".join(f"{item['face_a_id']}::{item['face_b_id']}" for item in point["supporting_interfaces"]) or "-"
        lines.append(f"| {point['ground_truth_id']} | {point['status']} | {point['reason'] or '-'} | {interfaces} |")
    return "\n".join(lines) + "\n"
