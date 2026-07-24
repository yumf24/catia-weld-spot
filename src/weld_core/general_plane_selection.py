"""Generic planar CAD-face selection by auditable geometry.

This module deliberately knows nothing about dataset names, templates,
reference STEP files, face indexes, or historical labels.  It accepts planar
faces with OCCT shapes and returns face/pair audit records based only on
parallelism, inter-plane gap, coarse spatial overlap and exact projected
CAD-boundary overlap.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
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
from .schema import FaceRecord, FacesDocument, FacesMeta, dump_document
from .step_geometry import StepFace

_ZERO_AREA_MM2 = 1e-9
_STRICT_GAP_LIMIT_MM = 0.2
_EXTENDED_GAP_LIMIT_MM = 1.5


@dataclass(frozen=True)
class GeneralSelectionParams:
    """Thresholds for generic planar face-pair selection."""

    max_normal_angle_deg: float = 0.5
    max_plane_gap_mm: float = 1.5
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
    area_mm2: float = 0.0


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
    gap_layer: str | None = None
    aabb_overlap_width_mm: float | None = None
    aabb_overlap_height_mm: float | None = None
    common_area_mm2: float = 0.0
    coverage_a: float = 0.0
    coverage_b: float = 0.0
    score: float = 0.0


def _gap_layer(plane_gap_mm: float | None) -> str | None:
    """Return the fixed audit layer for a measured inter-plane gap.

    This is audit metadata, not a selection threshold: production continues to
    use ``GeneralSelectionParams.max_plane_gap_mm`` (currently 1.5 mm).
    """

    if plane_gap_mm is None:
        return None
    if plane_gap_mm <= _STRICT_GAP_LIMIT_MM:
        return "strict"
    if plane_gap_mm <= _EXTENDED_GAP_LIMIT_MM:
        return "extended"
    return "beyond_extended"


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
        gap_layer=_gap_layer(plane_gap_mm),
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
        gap_layer=_gap_layer(measurement.plane_gap_mm),
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
                    area_mm2=face.area,
                    shape=face.shape,
                )
            )
    return faces


def _params_dict(params: GeneralSelectionParams) -> dict[str, Any]:
    return asdict(params)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def selected_faces_document(
    part_id: str,
    selected_faces: list[GeneralPlaneFace],
    *,
    warnings: list[str] | None = None,
) -> FacesDocument:
    """Serialize selected generic CAD faces as the pipeline's FacesDocument."""

    records = [
        FaceRecord(
            id=face.id,
            part=face.part,
            body="",
            surface_type="planar",
            area=face.area_mm2,
            normal=face.normal,
            plane_origin=face.plane_origin,
            centroid=face.centroid,
            vertices=list(face.vertices),
            manual_review=False,
            reason="generic_planar_selection",
        )
        for face in sorted(selected_faces, key=lambda item: item.id)
    ]
    return FacesDocument(
        meta=FacesMeta(
            part=part_id,
            unit="mm",
            context="product",
            warnings=warnings or [],
        ),
        faces=records,
    )


def run_registered_general_plane_selection(
    part_id: str,
    *,
    run_label: str = "generic-selection",
    params: GeneralSelectionParams | None = None,
    raw_root: Path | None = None,
    data_root: Path | None = None,
    run_parent: Path | None = None,
    now: datetime | None = None,
) -> Path:
    """Run generic selection from a registered primary STEP and write artifacts.

    Only the raw manifest's ``primary_model`` role is validated and consumed.
    Reference/evaluation-only inputs may exist in the same raw manifest but are
    intentionally absent from the created run's raw input registration.
    """

    from .data_layout import RAW_DATA_ROOT, DATA_ROOT, create_run, load_raw_manifest, update_run_manifest
    from .step_geometry import parse_step_faces

    params = params or GeneralSelectionParams()
    raw_root = raw_root or RAW_DATA_ROOT
    data_root = data_root or DATA_ROOT
    run_dir: Path | None = None
    try:
        run_dir, manifest = create_run(
            part_id,
            run_label,
            parameters={"general_selection": _params_dict(params)},
            raw_root=raw_root,
            data_root=data_root,
            run_parent=run_parent,
            input_roles=["primary_model"],
            now=now,
        )
        raw_manifest = load_raw_manifest(part_id, raw_root)
        primary_info = raw_manifest["inputs"]["primary_model"]
        primary_step = (raw_root / part_id / primary_info["path"]).resolve()

        all_faces = general_faces_from_step_groups(parse_step_faces(str(primary_step)))
        result = select_general_planar_faces(all_faces, params)
        selected_id_set = set(result.selected_face_ids)
        selected_faces = [face for face in all_faces if face.id in selected_id_set]
        audit_by_id = {audit.id: audit for audit in result.pair_audits}

        from .exact_planar_interface_regions import build_exact_planar_interface_region, write_exact_region

        faces_path = run_dir / "faces.general-selected.json"
        pair_audit_path = run_dir / "pair_audit.json"
        selection_audit_path = run_dir / "selection_audit.json"
        interface_audit_path = run_dir / "interface_region_audit.json"

        face_by_id = {face.id: face for face in all_faces}
        interface_regions: list[dict[str, Any]] = []
        region_ref_by_pair: dict[str, str] = {}
        for index, audit in enumerate(sorted((item for item in result.pair_audits if item.accepted), key=lambda item: item.id), start=1):
            face_a = face_by_id[audit.face_a_id]
            face_b = face_by_id[audit.face_b_id]
            measurement = exact_projected_pair_overlap(
                face_a, face_b,
                normal_angle_deg_value=audit.normal_angle_deg,
                plane_gap_mm_value=audit.plane_gap_mm,
            )
            region = build_exact_planar_interface_region(face_a, face_b, measurement)
            region_ref = f"exact_interface_regions/{index:04d}.brep"
            write_exact_region(region, run_dir / region_ref)
            region_ref_by_pair[audit.id] = region_ref
            interface_regions.append(
                {
                    "id": region.id,
                    "face_a_id": region.face_a_id,
                    "face_b_id": region.face_b_id,
                    "geometry_ref": region_ref,
                    "plane_origin": list(region.plane_origin),
                    "normal": list(region.normal),
                    "common_area_mm2": region.common_area_mm2,
                    "coverage_a": region.coverage_a,
                    "coverage_b": region.coverage_b,
                    "effective_width_mm": region.effective_width_mm,
                    "reason": None,
                }
            )

        dump_document(selected_faces_document(part_id, selected_faces), faces_path)
        _write_json(
            pair_audit_path,
            {
                "format_version": 1,
                "part_id": part_id,
                "run_id": manifest["run_id"],
                "parameters": _params_dict(params),
                "pairs": [
                    {**asdict(audit), "exact_region_ref": region_ref_by_pair.get(audit.id)}
                    for audit in result.pair_audits
                ],
            },
        )
        _write_json(
            interface_audit_path,
            {
                "format_version": 1,
                "part_id": part_id,
                "run_id": manifest["run_id"],
                "source": {"role": "primary_model"},
                "regions": interface_regions,
            },
        )
        _write_json(
            selection_audit_path,
            {
                "format_version": 1,
                "part_id": part_id,
                "run_id": manifest["run_id"],
                "source": {
                    "role": "primary_model",
                    "path": str(primary_step),
                    "sha256": manifest["raw_inputs"][0]["sha256"],
                },
                "parameters": _params_dict(params),
                "total_planar_faces": len(all_faces),
                "selected_face_count": len(selected_faces),
                "selected_faces": [
                    {
                        "face_id": face_id,
                        "supporting_pair_ids": list(result.supporting_pair_ids_by_face[face_id]),
                        "supporting_pair_gap_layers": [
                            {
                                "pair_id": pair_id,
                                "gap_layer": audit_by_id[pair_id].gap_layer,
                            }
                            for pair_id in result.supporting_pair_ids_by_face[face_id]
                        ],
                    }
                    for face_id in result.selected_face_ids
                ],
                "rejected_faces": [
                    {"face_id": face.id, "reason": "no_accepted_pair"}
                    for face in sorted(all_faces, key=lambda item: item.id)
                    if face.id not in selected_id_set
                ],
            },
        )

        from .data_layout import register_artifact

        register_artifact(run_dir, "faces.general-selected", faces_path, kind="faces_document")
        register_artifact(run_dir, "pair_audit", pair_audit_path, kind="json")
        register_artifact(run_dir, "selection_audit", selection_audit_path, kind="json")
        register_artifact(run_dir, "interface_region_audit", interface_audit_path, kind="json", count=len(interface_regions))
        update_run_manifest(
            run_dir,
            status="completed",
            completed_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        return run_dir
    except Exception as exc:
        if run_dir is not None:
            update_run_manifest(
                run_dir,
                status="failed",
                error=str(exc),
                failed_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            )
        raise
