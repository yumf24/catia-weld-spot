"""Two-dimensional coverage layouts for exact planar interface regions.

This module deliberately consumes the OCCT common shape produced by
``exact_planar_interface_regions``.  A projected bounding box is useful for
choosing a finite grid, but every emitted point is checked against the exact
face, so concavities and holes cannot silently turn into weld candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable

import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRep import BRep_Builder
from OCP.BRepGProp import BRepGProp
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepTools import BRepTools
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.TopAbs import TopAbs_FACE, TopAbs_IN, TopAbs_ON, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Pnt, gp_Pnt2d
from OCP.GProp import GProp_GProps

from .config import WeldParams
from .exact_planar_interface_regions import ExactPlanarInterfaceRegion
from .geometry import project_to_plane, unproject_from_plane
from .schema import BBox, Candidate


@dataclass(frozen=True)
class CoverageLayoutAudit:
    """Traceable result of laying out one exact interface region."""

    interface_id: str
    coverage_radius_mm: float
    grid_pitch_mm: float
    generated_count: int
    retained_count: int
    rejected_outside_exact_region: int
    layout_status: str
    layout_method: str
    probe_pitch_mm: float
    max_certificate_distance_mm: float
    max_projection_error_mm: float
    boundary_vertex_count: int
    max_boundary_distance_mm: float


def read_exact_region(record: dict, run_dir: str | Any) -> ExactPlanarInterfaceRegion:
    """Load a registered portable BREP region from an interface audit row."""

    from pathlib import Path

    path = Path(run_dir) / record["geometry_ref"]
    shape = TopoDS_Shape()
    if not BRepTools.Read_s(shape, str(path), BRep_Builder()):
        raise OSError(f"cannot read exact interface region {path}")
    if "plane_origin" not in record or "normal" not in record:
        raise ValueError(
            f"exact interface region audit {path} lacks its required layout frame; "
            "regenerate the generic plane-selection run"
        )
    return ExactPlanarInterfaceRegion(
        id=record["id"],
        face_a_id=record["face_a_id"],
        face_b_id=record["face_b_id"],
        plane_origin=tuple(float(value) for value in record["plane_origin"]),
        normal=tuple(float(value) for value in record["normal"]),
        common_area_mm2=float(record["common_area_mm2"]),
        coverage_a=float(record["coverage_a"]),
        coverage_b=float(record["coverage_b"]),
        effective_width_mm=float(record["effective_width_mm"]),
        shape=shape,
    )


def _faces(shape: Any) -> Iterable[Any]:
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        yield TopoDS.Face_s(explorer.Current())
        explorer.Next()


def _vertices(shape: Any) -> list[tuple[float, float, float]]:
    result: list[tuple[float, float, float]] = []
    explorer = TopExp_Explorer(shape, TopAbs_VERTEX)
    while explorer.More():
        point = BRep_Tool.Pnt_s(TopoDS.Vertex_s(explorer.Current()))
        result.append((float(point.X()), float(point.Y()), float(point.Z())))
        explorer.Next()
    return result


def _face_centres(shape: Any) -> list[tuple[float, float, float]]:
    """Return CAD surface centroids as robust interior probes for each face."""
    result = []
    for face in _faces(shape):
        properties = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, properties)
        centre = properties.CentreOfMass()
        result.append((float(centre.X()), float(centre.Y()), float(centre.Z())))
    return result


def point_in_exact_region(shape: Any, point: tuple[float, float, float], tolerance_mm: float = 1e-6) -> bool:
    """Return whether ``point`` lies in an OCCT face (including its boundary).

    Classifying in the face's native UV coordinates is important: projecting
    vertices into a plane and testing an AABB would accept holes and concave
    cut-outs.  Projection/classification failures are conservative rejects.
    """

    for face in _faces(shape):
        try:
            projector = GeomAPI_ProjectPointOnSurf(gp_Pnt(*point), BRep_Tool.Surface_s(face))
            if not projector.IsDone() or projector.LowerDistance() > tolerance_mm:
                continue
            u, v = projector.LowerDistanceParameters()
            state = BRepClass_FaceClassifier(face, gp_Pnt2d(u, v), tolerance_mm).State()
            if state in (TopAbs_IN, TopAbs_ON):
                return True
        except Exception:
            continue
    return False


def _candidate_bbox(region: ExactPlanarInterfaceRegion) -> BBox:
    vertices = np.asarray(_vertices(region.shape), dtype=float)
    if len(vertices) == 0:
        raise ValueError(f"exact region {region.id} has no vertices")
    lo, hi = vertices.min(axis=0), vertices.max(axis=0)
    return BBox(min=tuple(float(value) for value in lo), max=tuple(float(value) for value in hi))


def _distance(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return float(np.linalg.norm(np.asarray(left) - np.asarray(right)))


def _projection_error(point: tuple[float, float, float], region: ExactPlanarInterfaceRegion) -> float:
    normal = np.asarray(region.normal, dtype=float)
    normal /= np.linalg.norm(normal)
    return abs(float(np.dot(np.asarray(point) - np.asarray(region.plane_origin), normal)))


def layout_exact_region(
    region: ExactPlanarInterfaceRegion, params: WeldParams
) -> tuple[list[Candidate], CoverageLayoutAudit]:
    """Build a deterministic, exact-region-checked farthest-point layout.

    A dense finite set of UV-frame probes is generated from the authoritative
    BREP, classified in native UV, and greedily covered by its farthest probe.
    The resulting certificate describes that *complete layout pool*, before
    any later physical-station merging or ranking can create coverage debt.
    """

    coverage_radius = params.coverage_radius_mm
    if coverage_radius <= 0:
        raise ValueError("coverage_radius_mm must be positive")
    pitch = math.sqrt(2.0) * coverage_radius
    probe_pitch = coverage_radius / 2.0
    vertices_3d = _vertices(region.shape)
    if len(vertices_3d) < 3:
        raise ValueError(f"exact region {region.id} has insufficient vertices")
    vertices_2d = project_to_plane(vertices_3d, region.plane_origin, region.normal)
    lo, hi = vertices_2d.min(axis=0), vertices_2d.max(axis=0)

    # Fine cell-centred probes provide deterministic coverage witnesses;
    # explicit BREP vertices ensure thin strips and boundary tips cannot be
    # missed merely because they fall between cell centres.
    xs = np.arange(lo[0] + probe_pitch / 2.0, hi[0], probe_pitch)
    ys = np.arange(lo[1] + probe_pitch / 2.0, hi[1], probe_pitch)
    samples_2d = [(float(x), float(y)) for x in xs for y in ys]
    samples_2d.extend((float(x), float(y)) for x, y in vertices_2d)
    center = ((lo + hi) / 2.0).reshape(1, 2)
    samples_2d.append((float(center[0, 0]), float(center[0, 1])))

    # Stable de-duplication retains audit reproducibility independent of OCCT
    # explorer order and avoids duplicate corner/grid candidates.
    unique_samples = sorted({(round(x, 9), round(y, 9)) for x, y in samples_2d})
    generated = len(unique_samples)
    accepted: list[tuple[float, float, float]] = []
    rejected = 0
    for sample in unique_samples:
        point = unproject_from_plane(np.asarray([sample]), region.plane_origin, region.normal)[0]
        position = (float(point[0]), float(point[1]), float(point[2]))
        if point_in_exact_region(region.shape, position):
            accepted.append(position)
        else:
            rejected += 1

    # The exact face centre is a BREP-derived interior witness.  It repairs
    # cases where a thin or heavily trimmed face has no retained rectangular
    # grid probe, without ever fabricating an AABB point.
    for point in _face_centres(region.shape):
        if point_in_exact_region(region.shape, point):
            accepted.append(point)

    if not accepted:
        raise ValueError(f"exact region {region.id} has no UV-classified layout probes")

    accepted = sorted(set(accepted))
    boundary_points = sorted({point for point in vertices_3d if point_in_exact_region(region.shape, point)})

    # Seed deterministically with exact boundary witnesses, then repeatedly select the currently farthest
    # exact probe until every certificate witness is within the coverage
    # radius.  Tie-breaking is the stable projected-coordinate ordering above.
    selected = boundary_points or [accepted[0]]
    nearest = [min(_distance(point, prior) for prior in selected) for point in accepted]
    while max(nearest) > coverage_radius + 1e-9:
        index = max(range(len(accepted)), key=lambda item: (nearest[item], tuple(-v for v in accepted[item])))
        selected.append(accepted[index])
        nearest = [min(old, _distance(point, accepted[index])) for point, old in zip(accepted, nearest)]

    max_certificate_distance = max(nearest, default=0.0)
    max_projection_error = max((_projection_error(point, region) for point in selected), default=0.0)
    max_boundary_distance = max(
        (min(_distance(vertex, point) for point in selected) for vertex in boundary_points), default=0.0
    )
    # Region frames originate from STEP-derived face normals, whose serialized
    # precision can leave an exact BREP boundary a few microns off that plane.
    # Keep this tolerance far below the 10 mm coverage radius and publish the
    # measured value rather than silently treating it as zero.
    if max_projection_error > 1e-3:
        raise ValueError(f"exact region {region.id} layout projection error exceeds tolerance")

    bbox = _candidate_bbox(region)
    reason = (
        f"exact 2d coverage, interface={region.id}, radius={coverage_radius:.3f}mm, "
        f"pitch={pitch:.3f}mm"
    )
    candidates = [
        Candidate(
            id=f"{region.id}#{index}",
            position=position,
            faces=[region.face_a_id, region.face_b_id],
            layer_type="two_layer",
            layer_count=2,
            supporting_interfaces=[region.id],
            confidence_tier="high",
            spacing_mm=pitch,
            region_bbox=bbox,
            reason=reason,
        )
        for index, position in enumerate(selected)
    ]
    return candidates, CoverageLayoutAudit(
        interface_id=region.id,
        coverage_radius_mm=coverage_radius,
        grid_pitch_mm=pitch,
        generated_count=generated,
        retained_count=len(candidates),
        rejected_outside_exact_region=rejected,
        layout_status="certified",
        layout_method="exact_uv_adaptive_farthest_point_v1",
        probe_pitch_mm=probe_pitch,
        max_certificate_distance_mm=max_certificate_distance,
        max_projection_error_mm=max_projection_error,
        boundary_vertex_count=len(vertices_3d),
        max_boundary_distance_mm=max_boundary_distance,
    )
