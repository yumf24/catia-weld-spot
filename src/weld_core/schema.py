"""Data contracts for the weld-candidate pipeline.

Defines the ``faces.json`` (extractor output / core input) and
``candidates.json`` (core output / writer input) schemas using pydantic,
plus small load/dump helpers. Keeping every field in one place means the
CATIA extractor, the algorithm core and the CATIA writer all agree on the
wire format.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

Vec3 = tuple[float, float, float]

SCHEMA_VERSION = "0.1"


class FaceRecord(BaseModel):
    """A single face extracted from CATIA.

    ``normal`` is a unit vector whose sign is not guaranteed (the core
    compares normals ignoring direction). ``vertices`` may be empty for
    curved edges or when topology access failed; such faces are flagged
    with ``manual_review``.
    """

    id: str
    part: str
    body: str
    surface_type: Literal["planar", "non_planar"] = "planar"
    area: float = 0.0
    normal: Vec3 = (0.0, 0.0, 1.0)
    plane_origin: Vec3 = (0.0, 0.0, 0.0)
    centroid: Vec3 = (0.0, 0.0, 0.0)
    vertices: list[Vec3] = Field(default_factory=list)
    manual_review: bool = False
    reason: str = ""


class FacesMeta(BaseModel):
    part: str = ""
    unit: str = "mm"
    extractor_version: str = SCHEMA_VERSION
    context: Literal["part", "product"] = "part"
    warnings: list[str] = Field(default_factory=list)


class FacesDocument(BaseModel):
    """Top-level ``faces.json`` document."""

    meta: FacesMeta = Field(default_factory=FacesMeta)
    faces: list[FaceRecord] = Field(default_factory=list)


class BBox(BaseModel):
    min: Vec3
    max: Vec3


class Candidate(BaseModel):
    """A single generated weld point candidate."""

    id: str
    position: Vec3
    faces: list[str] = Field(default_factory=list)
    layer_type: Literal["two_layer", "three_layer"] = "two_layer"
    spacing_mm: float = 0.0
    region_bbox: Optional[BBox] = None
    reason: str = ""


class CandidatesMeta(BaseModel):
    source: str = ""
    core_version: str = SCHEMA_VERSION
    params: dict = Field(default_factory=dict)


class CandidatesDocument(BaseModel):
    """Top-level ``candidates.json`` document."""

    meta: CandidatesMeta = Field(default_factory=CandidatesMeta)
    candidates: list[Candidate] = Field(default_factory=list)


class GroundTruthPoint(BaseModel):
    """A single real (ground-truth) weld point, e.g. parsed from a
    weld-spot marker STEP file such as ``raw_data/component/SPOT.step``."""

    id: str
    position: Vec3
    radius: float = 0.0
    label: str = ""


class GroundTruthMeta(BaseModel):
    source: str = ""
    unit: str = "mm"
    extractor_version: str = SCHEMA_VERSION


class GroundTruthDocument(BaseModel):
    """Top-level ``ground_truth.json`` document."""

    meta: GroundTruthMeta = Field(default_factory=GroundTruthMeta)
    points: list[GroundTruthPoint] = Field(default_factory=list)


class EvalMatch(BaseModel):
    """One ground-truth point matched to one candidate within tolerance."""

    ground_truth_id: str
    candidate_id: str
    distance_mm: float


class EvalSummary(BaseModel):
    num_ground_truth: int = 0
    num_candidates: int = 0
    true_positives: int = 0
    false_negatives: int = 0
    false_positives: int = 0
    recall: float = 0.0
    precision: float = 0.0
    mean_error_mm: float = 0.0
    max_error_mm: float = 0.0


class EvaluationMeta(BaseModel):
    ground_truth_source: str = ""
    candidates_source: str = ""
    tolerance_mm: float = 0.0
    core_version: str = SCHEMA_VERSION


class EvaluationDocument(BaseModel):
    """Top-level ``evaluation.json`` document."""

    meta: EvaluationMeta = Field(default_factory=EvaluationMeta)
    summary: EvalSummary = Field(default_factory=EvalSummary)
    matches: list[EvalMatch] = Field(default_factory=list)
    unmatched_ground_truth: list[str] = Field(default_factory=list)
    unmatched_candidates: list[str] = Field(default_factory=list)


def load_faces(path: str | Path) -> FacesDocument:
    return FacesDocument.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_candidates(path: str | Path) -> CandidatesDocument:
    return CandidatesDocument.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_ground_truth(path: str | Path) -> GroundTruthDocument:
    return GroundTruthDocument.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_evaluation(path: str | Path) -> EvaluationDocument:
    return EvaluationDocument.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def dump_document(doc: BaseModel, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(doc.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
