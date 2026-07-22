"""Runtime selection of planar CAD faces from a frozen template.

Unlike template construction this module never opens the human reference
STEP.  It validates the registered primary input and every frozen face
identity against a fresh parse of that one primary STEP before emitting a
``FacesDocument``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .plane_reference_labels import IndexedStepFace, indexed_planar_faces
from .plane_selection_template import TemplateValidationError, boundary_fingerprint, validate_template
from .schema import FaceRecord, FacesDocument, FacesMeta


class TemplateSelectionError(ValueError):
    """Raised when a frozen template cannot be applied safely."""


def template_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_template(path: Path) -> dict[str, Any]:
    try:
        template = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TemplateSelectionError(f"cannot read selection template {path}: {exc}") from exc
    try:
        validate_template(template)
    except TemplateValidationError as exc:
        raise TemplateSelectionError(str(exc)) from exc
    return template


def validate_primary_sha(template: dict[str, Any], actual_sha256: str) -> None:
    """Fail closed when the runtime primary STEP differs from the template."""
    if actual_sha256 != template["source_sha256"]:
        raise TemplateSelectionError(
            "primary STEP SHA-256 differs; rebuild the frozen template before selecting faces"
        )


def select_template_planes(template: dict[str, Any], source_groups: dict[str, list]) -> tuple[FacesDocument, dict[str, Any]]:
    """Validate template identities and return selected faces plus full audit.

    All primary planar faces appear in the audit: selected entries record their
    frozen identity while every other plane is explicitly excluded because it
    is absent from the frozen template.  Any template/index/fingerprint error
    raises, so callers can guarantee that no partial selection is written.
    """
    try:
        validate_template(template)
    except TemplateValidationError as exc:
        raise TemplateSelectionError(str(exc)) from exc

    indexed = indexed_planar_faces(source_groups)
    available = {(face.part, face.index): face for face in indexed}
    requested = {(entry["part"], entry["step_face_index"]): entry for entry in template["selected_faces"]}
    selected: list[FaceRecord] = []
    audit_by_identity: dict[tuple[str, int], dict[str, Any]] = {}

    for identity, entry in requested.items():
        source = available.get(identity)
        if source is None:
            raise TemplateSelectionError(f"template face index is absent or no longer planar: {identity[0]}/{identity[1]}")
        actual_fingerprint = boundary_fingerprint(source.face.vertices)
        if actual_fingerprint != entry["boundary_fingerprint"]:
            raise TemplateSelectionError(f"template face fingerprint differs: {identity[0]}/{identity[1]}")
        selected.append(FaceRecord(
            id=source.id,
            part=source.part,
            body="unknown",
            surface_type="planar",
            area=source.face.area,
            normal=source.face.normal,
            plane_origin=source.face.centroid,
            centroid=source.face.centroid,
            vertices=source.face.vertices,
            manual_review=False,
            reason="selected_from_frozen_template",
        ))
        audit_by_identity[identity] = {
            "face_id": source.id, "part": source.part, "step_face_index": source.index,
            "status": "selected", "reason": "template_identity_and_fingerprint_verified",
        }

    for source in indexed:
        identity = (source.part, source.index)
        audit_by_identity.setdefault(identity, {
            "face_id": source.id, "part": source.part, "step_face_index": source.index,
            "status": "excluded", "reason": "not_in_frozen_template",
        })
    audit = {
        "format_version": 1,
        "part_id": template["part_id"],
        "template_source_sha256": template["source_sha256"],
        "summary": {
            "primary_planar_faces": len(indexed), "selected_faces": len(selected),
            "excluded_faces": len(indexed) - len(selected), "passed": True,
        },
        "faces": [audit_by_identity[(face.part, face.index)] for face in indexed],
    }
    selected.sort(key=lambda face: face.id)
    return FacesDocument(meta=FacesMeta(part=template["part_id"], context="product"), faces=selected), audit
