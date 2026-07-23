"""Create the isolated, truth-free candidate run for ``component``.

This module is deliberately limited to the candidate-generation half of the
component weld evaluation.  It loads only the registered primary STEP model;
ground-truth markers and every evaluation artifact are intentionally absent
from this module so they cannot influence candidate generation.
"""

from __future__ import annotations

from pathlib import Path

from .config import WeldParams
from .data_layout import (
    DATA_ROOT,
    create_run,
    register_artifact,
    sha256_file,
    update_run_manifest,
)
from .pipeline import run
from .schema import FaceRecord, FacesDocument, FacesMeta, dump_document
from .step_geometry import StepFace, parse_step_faces


COMPONENT_PART_ID = "component"
COMPONENT_EVALUATION_RUN_ROOT = DATA_ROOT / "component-weld-evaluation"
FROZEN_COMPONENT_WELD_PARAMS = WeldParams()


def planar_faces_document(step_path: Path) -> FacesDocument:
    """Extract serializable planar faces from one primary STEP model."""
    grouped = parse_step_faces(str(step_path))
    records: list[FaceRecord] = []
    for part_name in sorted(grouped):
        planar = (face for face in grouped[part_name] if face.is_planar and len(face.vertices) >= 3)
        for index, face in enumerate(planar, start=1):
            records.append(_as_face_record(part_name, index, face))
    return FacesDocument(
        meta=FacesMeta(part=COMPONENT_PART_ID),
        faces=records,
    )


def _as_face_record(part_name: str, index: int, face: StepFace) -> FaceRecord:
    return FaceRecord(
        id=f"{part_name}/STEP/face_{index:05d}",
        part=part_name,
        body="STEP",
        surface_type="planar",
        area=face.area,
        normal=face.normal,
        plane_origin=face.centroid,
        centroid=face.centroid,
        vertices=face.vertices,
    )


def create_component_candidate_run(label: str = "candidate") -> Path:
    """Create a completed isolated run using only ``component.step``."""
    run_dir, _manifest = create_run(
        COMPONENT_PART_ID,
        label,
        input_roles=("primary_model",),
        run_parent=COMPONENT_EVALUATION_RUN_ROOT,
        parameters={"weld_params": FROZEN_COMPONENT_WELD_PARAMS.as_dict()},
    )
    try:
        primary_step = Path(_manifest["raw_inputs"][0]["path"])
        faces = planar_faces_document(primary_step)
        faces_path = run_dir / "faces.planar.json"
        dump_document(faces, faces_path)
        register_artifact(
            run_dir,
            "faces.planar",
            faces_path,
            kind="json",
            sha256=sha256_file(faces_path),
            count=len(faces.faces),
        )

        candidates = run(faces, FROZEN_COMPONENT_WELD_PARAMS)
        candidates_path = run_dir / "candidates.json"
        dump_document(candidates, candidates_path)
        register_artifact(
            run_dir,
            "candidates",
            candidates_path,
            kind="json",
            sha256=sha256_file(candidates_path),
            count=len(candidates.candidates),
        )
        update_run_manifest(run_dir, status="completed")
    except Exception:
        update_run_manifest(run_dir, status="failed")
        raise
    return run_dir
