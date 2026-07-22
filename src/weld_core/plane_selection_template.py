"""Frozen plane-selection template construction and contract validation."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from .plane_reference_labels import IndexedStepFace

FORMAT_VERSION = 1
MIN_SOURCE_COVERAGE = 0.95


class TemplateValidationError(ValueError):
    """Raised when a frozen selection template violates its contract."""


def _rounded_vertices(vertices: Iterable[tuple[float, float, float]]) -> list[list[float]]:
    return sorted([[round(float(value), 6) for value in point] for point in vertices])


def boundary_fingerprint(vertices: Iterable[tuple[float, float, float]]) -> dict[str, Any]:
    """Return a stable, orientation-independent fingerprint for a face boundary."""
    rounded = _rounded_vertices(vertices)
    encoded = json.dumps(rounded, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return {"vertex_count": len(rounded), "vertices_sha256": hashlib.sha256(encoded).hexdigest()}


def build_template(label_result: dict, source_faces: Iterable[IndexedStepFace], raw_inputs: list[dict]) -> dict:
    """Convert exact S03 labels into a serializable frozen-template contract."""
    if not label_result.get("summary", {}).get("passed"):
        raise TemplateValidationError("cannot freeze a template from failed or ambiguous labels")
    source_by_id = {source.id: source for source in source_faces}
    hashes = {row["role"]: row["sha256"] for row in raw_inputs}
    try:
        source_sha = hashes["primary_model"]
        reference_sha = hashes["surface_reference"]
    except KeyError as exc:
        raise TemplateValidationError("raw inputs must include primary_model and surface_reference") from exc
    selected_faces = []
    for label in label_result["labels"]:
        source = source_by_id.get(label["source_face_id"])
        if source is None:
            raise TemplateValidationError(f"label source face is missing: {label['source_face_id']}")
        face = source.face
        selected_faces.append({
            "part": source.part,
            "step_face_index": source.index,
            "area_mm2": face.area,
            "centroid": list(face.centroid),
            "normal": list(face.normal),
            "boundary_fingerprint": boundary_fingerprint(face.vertices),
            "source_coverage": label["source_coverage"],
            "reference_coverage": label["reference_coverage"],
            "reference_face_id": label["reference_face_id"],
            "reference_face_index": label["reference_face_index"],
        })
    template = {
        "format_version": FORMAT_VERSION,
        "part_id": label_result["part_id"],
        "source_sha256": source_sha,
        "reference_sha256": reference_sha,
        "thresholds": label_result["thresholds"],
        "selected_faces": selected_faces,
        "label_build_summary": label_result["summary"],
    }
    validate_template(template)
    return template


def validate_template(template: dict) -> None:
    """Reject incomplete, non-auditable, or unsafe frozen selection data."""
    required = {"format_version", "part_id", "source_sha256", "reference_sha256", "thresholds", "selected_faces"}
    missing = required - template.keys()
    if missing:
        raise TemplateValidationError(f"template missing fields: {', '.join(sorted(missing))}")
    if template["format_version"] != FORMAT_VERSION:
        raise TemplateValidationError("unsupported template format_version")
    for key in ("source_sha256", "reference_sha256"):
        value = template[key]
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise TemplateValidationError(f"invalid {key}")
    thresholds = template["thresholds"]
    if not isinstance(thresholds, dict) or thresholds.get("source_coverage_min", 0.0) < MIN_SOURCE_COVERAGE:
        raise TemplateValidationError("template source coverage threshold is unsafe")
    identities: set[tuple[str, int]] = set()
    for face in template["selected_faces"]:
        required_face = {
            "part", "step_face_index", "area_mm2", "centroid", "normal", "boundary_fingerprint",
            "source_coverage", "reference_coverage", "reference_face_id", "reference_face_index",
        }
        missing_face = required_face - face.keys()
        if missing_face:
            raise TemplateValidationError(f"selected face missing fields: {', '.join(sorted(missing_face))}")
        identity = (face["part"], face["step_face_index"])
        if identity in identities:
            raise TemplateValidationError(f"duplicate selected face identity: {identity[0]}/{identity[1]}")
        identities.add(identity)
        fingerprint = face["boundary_fingerprint"]
        if not isinstance(fingerprint, dict) or fingerprint.get("vertex_count", 0) < 3:
            raise TemplateValidationError("selected face has invalid boundary fingerprint")
        digest = fingerprint.get("vertices_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise TemplateValidationError("selected face has invalid boundary fingerprint hash")
        if face["source_coverage"] < MIN_SOURCE_COVERAGE:
            raise TemplateValidationError("selected face source coverage is below contract minimum")
