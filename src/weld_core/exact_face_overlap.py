"""Exact overlap measurements for already-qualified coplanar CAD faces.

Projected AABBs remain useful to cheaply find candidate pairs, but they are
not a geometric acceptance condition.  This module measures the actual common
CAD boundary with OCCT boolean operations and surface properties.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Fuse
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps


MAX_NORMAL_ANGLE_DEG = 0.5
MAX_PLANE_DISTANCE_MM = 0.05
_ZERO_AREA_MM2 = 1e-9
# Independent STEP exports of the same face often differ at roughly 1e-6 mm
# in their trimmed-edge representation.  OCCT's default boolean tolerance is
# too small for that representation noise; this is deliberately much tighter
# than the 0.05 mm coplanarity contract and is not an acceptance tolerance.
_BOOLEAN_FUZZY_TOL_MM = 3e-3


@dataclass(frozen=True)
class CoplanarFacePair:
    """Two faces plus their independently measured supporting-plane errors."""

    source: Any
    reference: Any
    normal_angle_deg: float
    plane_distance_mm: float


@dataclass(frozen=True)
class ExactFaceOverlap:
    """Exact common area and bidirectional coverage for one CAD-face pair."""

    common_area_mm2: float
    source_coverage: float
    reference_coverage: float
    source_area_mm2: float
    reference_area_mm2: float
    reason: str | None = None

    @property
    def matched(self) -> bool:
        return self.reason is None and self.common_area_mm2 > _ZERO_AREA_MM2


def surface_area_mm2(face: Any) -> float:
    """Return an OCCT face/shape's surface area in the STEP model's mm units."""
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return float(props.Mass())


def _empty(source_area: float, reference_area: float, reason: str) -> ExactFaceOverlap:
    return ExactFaceOverlap(0.0, 0.0, 0.0, source_area, reference_area, reason)


def _common_shape(left: Any, right: Any) -> Any:
    operation = BRepAlgoAPI_Common(left, right)
    operation.SetFuzzyValue(_BOOLEAN_FUZZY_TOL_MM)
    operation.Build()
    return operation.Shape()


def exact_face_overlap(pair: CoplanarFacePair) -> ExactFaceOverlap:
    """Measure exact common area, rejecting an invalid coplanar qualification.

    The caller owns normal/plane-distance measurement; keeping those values in
    ``CoplanarFacePair`` makes the acceptance threshold auditable alongside
    the boolean-boundary result.
    """
    source_area = surface_area_mm2(pair.source)
    reference_area = surface_area_mm2(pair.reference)
    if pair.normal_angle_deg > MAX_NORMAL_ANGLE_DEG:
        return _empty(source_area, reference_area, "normal_angle_exceeds_tolerance")
    if pair.plane_distance_mm > MAX_PLANE_DISTANCE_MM:
        return _empty(source_area, reference_area, "plane_distance_exceeds_tolerance")
    if source_area <= _ZERO_AREA_MM2 or reference_area <= _ZERO_AREA_MM2:
        return _empty(source_area, reference_area, "zero_area_input")

    try:
        common = _common_shape(pair.source, pair.reference)
        common_area = surface_area_mm2(common)
    except Exception as exc:  # OCCT exposes algorithm failures as varied Python exceptions.
        return _empty(source_area, reference_area, f"boolean_common_failed:{type(exc).__name__}")
    if common_area <= _ZERO_AREA_MM2:
        return _empty(source_area, reference_area, "zero_area_intersection")
    return ExactFaceOverlap(
        common_area_mm2=common_area,
        source_coverage=common_area / source_area,
        reference_coverage=common_area / reference_area,
        source_area_mm2=source_area,
        reference_area_mm2=reference_area,
    )


def source_union_coverage(pairs: Iterable[CoplanarFacePair]) -> ExactFaceOverlap:
    """Measure one source face's coverage by the union of reference faces.

    References may overlap each other.  Their individual common areas must
    therefore never be summed; the intermediate common shapes are fused first
    so shared material is counted once.
    """
    checked = list(pairs)
    if not checked:
        raise ValueError("at least one source/reference pair is required")
    source = checked[0].source
    if any(pair.source.IsSame(source) is False for pair in checked[1:]):
        raise ValueError("all pairs must share the same source face")

    source_area = surface_area_mm2(source)
    overlaps = [exact_face_overlap(pair) for pair in checked]
    valid_pairs = [pair for pair, overlap in zip(checked, overlaps) if overlap.matched]
    if not valid_pairs:
        reason = overlaps[0].reason or "zero_area_intersection"
        return _empty(source_area, 0.0, reason)
    try:
        union = _common_shape(source, valid_pairs[0].reference)
        for pair in valid_pairs[1:]:
            common = _common_shape(source, pair.reference)
            fuse = BRepAlgoAPI_Fuse(union, common)
            fuse.SetFuzzyValue(_BOOLEAN_FUZZY_TOL_MM)
            fuse.Build()
            union = fuse.Shape()
        union_area = surface_area_mm2(union)
    except Exception as exc:
        return _empty(source_area, 0.0, f"boolean_union_failed:{type(exc).__name__}")
    if union_area <= _ZERO_AREA_MM2:
        return _empty(source_area, 0.0, "zero_area_intersection")
    return ExactFaceOverlap(
        common_area_mm2=union_area,
        source_coverage=union_area / source_area,
        reference_coverage=0.0,
        source_area_mm2=source_area,
        reference_area_mm2=0.0,
    )
