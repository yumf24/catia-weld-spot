"""Exact, auditable planar interface regions.

The generic selector uses a projected AABB only as a cheap reject-before-OCCT
check.  This module materializes the *actual* OCCT common face for every
accepted pair so later layout stages have a stable geometry reference instead
of silently reconstructing an AABB rectangle.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepTools import BRepTools
from OCP.TopAbs import TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.BRep import BRep_Tool
from OCP.TopoDS import TopoDS

from .exact_face_overlap import _BOOLEAN_FUZZY_TOL_MM, surface_area_mm2
from .general_plane_selection import (
    ExactPairMeasurement,
    GeneralPlaneFace,
    _project_shape_to_plane,
)
from .geometry import project_to_plane


@dataclass(frozen=True)
class ExactPlanarInterfaceRegion:
    """One projected OCCT common region with its audit measurements."""

    id: str
    face_a_id: str
    face_b_id: str
    plane_origin: tuple[float, float, float]
    normal: tuple[float, float, float]
    common_area_mm2: float
    coverage_a: float
    coverage_b: float
    effective_width_mm: float
    shape: Any


def _common_shape(left: Any, right: Any) -> Any:
    operation = BRepAlgoAPI_Common(left, right)
    operation.SetFuzzyValue(_BOOLEAN_FUZZY_TOL_MM)
    operation.Build()
    return operation.Shape()


def _effective_width_mm(shape: Any, origin: tuple[float, float, float], normal: tuple[float, float, float]) -> float:
    """Return the smaller non-zero exact-region extent in its support plane.

    This is audit evidence, not the old AABB acceptance rule: the shape passed
    here is the OCCT boolean common region.  Later 2-D coverage layout will
    use the saved BREP directly for holes and concavities.
    """

    vertices: list[tuple[float, float, float]] = []
    explorer = TopExp_Explorer(shape, TopAbs_VERTEX)
    while explorer.More():
        point = BRep_Tool.Pnt_s(TopoDS.Vertex_s(explorer.Current()))
        vertices.append((float(point.X()), float(point.Y()), float(point.Z())))
        explorer.Next()
    if len(vertices) < 3:
        return 0.0
    projected = project_to_plane(vertices, origin, normal)
    extents = np.ptp(projected, axis=0)
    positive = sorted(float(value) for value in extents if value > 1e-9)
    return positive[0] if positive else 0.0


def build_exact_planar_interface_region(
    face_a: GeneralPlaneFace,
    face_b: GeneralPlaneFace,
    measurement: ExactPairMeasurement,
) -> ExactPlanarInterfaceRegion:
    """Materialize an accepted pair's projected exact common CAD region."""

    if not measurement.matched:
        raise ValueError("cannot build an exact region for an unmatched pair")
    projected_b = _project_shape_to_plane(face_b, face_a)
    common = _common_shape(face_a.shape, projected_b)
    common_area = surface_area_mm2(common)
    if common_area <= 1e-9:
        raise ValueError("exact common region has zero area")
    return ExactPlanarInterfaceRegion(
        id=f"{face_a.id}::{face_b.id}",
        face_a_id=face_a.id,
        face_b_id=face_b.id,
        plane_origin=face_a.plane_origin,
        normal=face_a.normal,
        common_area_mm2=common_area,
        coverage_a=measurement.coverage_a,
        coverage_b=measurement.coverage_b,
        effective_width_mm=_effective_width_mm(common, face_a.plane_origin, face_a.normal),
        shape=common,
    )


def write_exact_region(region: ExactPlanarInterfaceRegion, path: Path) -> None:
    """Write the OCCT common face as a portable BREP geometry reference."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if not BRepTools.Write_s(region.shape, str(path)):
        raise OSError(f"failed to write exact interface region {path}")
