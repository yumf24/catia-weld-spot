"""STEP + OCP (OpenCASCADE) offline parser: vertex/face completion for faces.json.

Solves the vertex-extraction gap documented in DEVLOG.md ("CATIA COM
Selection.Search face-scoping is unreliable, faces[].vertices is always
empty"). This module reads a STEP export of the same document (see
``Document.ExportData`` in pycatia, producing a managed run's ``component.stp``
for now) and returns, per CATIA PartNumber, the real face vertices/area/
centroid/planarity — entirely offline, no CATIA/pycatia/pywin32 involved.

Two pitfalls found and handled here (see PLAN.md "关键技术结论" #4):

1. **Part name mapping.** ``cadquery``'s flat ``importStep`` collapses the
   whole assembly into one compound and loses part names. We instead walk
   the STEP file's XCAF assembly tree (``STEPCAFControl_Reader`` +
   ``XCAFDoc_ShapeTool``), which preserves each part's name — verified to
   match the CATIA PartNumber exactly (e.g. ``MDAU54VBV4`` -> 179 faces in
   both STEP and the pycatia COM extractor).
2. **Global coordinates.** Each part occurrence in the assembly carries its
   own ``TopLoc_Location`` (assembly placement). Resolving a referenced part
   without composing the ancestor locations yields vertices in the part's
   local modeling frame, not the assembly's global frame that CATIA COM
   measurements use — verified by comparing against the fully-assembled
   compound's coordinates for the same vertex (exact match once locations
   are accumulated and applied via ``TopoDS_Shape.Moved``).
3. **Planarity.** STEP export writes every face (including true planes) as
   a generic parametric surface — ``BRepAdaptor_Surface.GetType()`` never
   reports ``GeomAbs_Plane`` on these files. Planarity is instead decided by
   a vertex plane fit (``weld_core.geometry.fit_plane_residual``). A face
   with exactly 3 vertices is trivially "coplanar" by construction, so an
   extra interior surface sample (UV midpoint) is always added before the
   fit to catch curved triangular faces.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_Sphere
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_Label, TDF_LabelSequence
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_FACE, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool

from .geometry import fit_plane_residual

Vec3 = tuple[float, float, float]

# Generic shape-container names XCAF assigns that carry no part identity;
# skip these when propagating "current part name" down the assembly tree.
_GENERIC_NAMES = {"", "COMPOUND", "SHELL", "SOLID"}

# Planarity threshold: max distance (mm) of any vertex/sample point to the
# fitted plane. Matches the value validated in DEVLOG against real parts.
PLANAR_RESIDUAL_TOL_MM = 0.01

# Vertex dedup tolerance (mm): shared edges visit the same vertex from each
# adjacent face's wire, producing exact or near-exact duplicate points.
_VERTEX_DEDUP_TOL_MM = 1e-6


@dataclass
class StepFace:
    """One face extracted from a STEP assembly, in global (assembly) coordinates."""

    part_name: str
    vertices: list[Vec3] = field(default_factory=list)
    centroid: Vec3 = (0.0, 0.0, 0.0)
    normal: Vec3 = (0.0, 0.0, 1.0)
    area: float = 0.0
    is_planar: bool = False
    max_residual: float = 0.0


def _name_of(label: TDF_Label) -> str:
    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return attr.Get().ToExtString()
    return ""


def _unique_vertices(face) -> list[Vec3]:
    seen: dict[Vec3, None] = {}
    vexp = TopExp_Explorer(face, TopAbs_VERTEX)
    while vexp.More():
        v = TopoDS.Vertex_s(vexp.Current())
        p = BRep_Tool.Pnt_s(v)
        key = (
            round(p.X() / _VERTEX_DEDUP_TOL_MM) * _VERTEX_DEDUP_TOL_MM,
            round(p.Y() / _VERTEX_DEDUP_TOL_MM) * _VERTEX_DEDUP_TOL_MM,
            round(p.Z() / _VERTEX_DEDUP_TOL_MM) * _VERTEX_DEDUP_TOL_MM,
        )
        seen.setdefault(key, (p.X(), p.Y(), p.Z()))
        vexp.Next()
    return list(seen.values())


def _face_to_step_face(face, part_name: str) -> StepFace:
    vertices = _unique_vertices(face)

    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    area = float(props.Mass())
    com = props.CentreOfMass()
    centroid = (float(com.X()), float(com.Y()), float(com.Z()))

    sample_points = list(vertices)
    try:
        umin, umax, vmin, vmax = BRepTools.UVBounds_s(face)
        surf = BRep_Tool.Surface_s(face)
        # Two interior points at asymmetric (u, v) fractions rather than one
        # exact midpoint: a single midpoint can sit on a symmetry plane of
        # the underlying surface (e.g. for a periodic full-revolution
        # surface like a sphere, (umin+umax)/2 falls on the same meridian
        # plane as the pole vertices, which trivially "fits" and masks
        # curvature). Two asymmetric fractions avoid coinciding with any
        # such plane by construction.
        for uf, vf in ((0.35, 0.65), (0.7, 0.3)):
            pnt = surf.Value(umin + uf * (umax - umin), vmin + vf * (vmax - vmin))
            sample_points.append((float(pnt.X()), float(pnt.Y()), float(pnt.Z())))
    except Exception:
        pass

    if len(sample_points) >= 3:
        normal, _origin, residual = fit_plane_residual(sample_points)
        is_planar = residual < PLANAR_RESIDUAL_TOL_MM
    else:
        normal, residual, is_planar = (0.0, 0.0, 1.0), 0.0, False

    return StepFace(
        part_name=part_name,
        vertices=vertices,
        centroid=centroid,
        normal=(float(normal[0]), float(normal[1]), float(normal[2])),
        area=area,
        is_planar=is_planar,
        max_residual=float(residual),
    )


def _walk(shape_tool, label: TDF_Label, current_name: str, loc: TopLoc_Location, out: list, face_fn) -> None:
    """Recurse the XCAF assembly tree, calling ``face_fn(face, part_name)`` on
    every leaf face (in global/assembly coordinates) and collecting whatever
    it returns (skipping ``None``) into ``out``.

    Shared by ``parse_step_faces`` (planar-face extraction) and
    ``parse_step_spheres`` (weld-spot marker extraction) so the assembly
    traversal / name resolution / location composition — the tricky, already
    validated part (see module docstring pitfalls 1-2) — is written once.
    """
    if shape_tool.IsReference_s(label):
        my_loc = shape_tool.GetLocation_s(label)
        combined = loc.Multiplied(my_loc)
        ref_label = TDF_Label()
        shape_tool.GetReferredShape_s(label, ref_label)
        _walk(shape_tool, ref_label, current_name, combined, out, face_fn)
        return

    name = _name_of(label)
    effective_name = name if name not in _GENERIC_NAMES else current_name

    if shape_tool.IsSimpleShape_s(label):
        shape = shape_tool.GetShape_s(label).Moved(loc)
        fexp = TopExp_Explorer(shape, TopAbs_FACE)
        while fexp.More():
            face = TopoDS.Face_s(fexp.Current())
            result = face_fn(face, effective_name or "UNNAMED")
            if result is not None:
                out.append(result)
            fexp.Next()
        return

    children = TDF_LabelSequence()
    shape_tool.GetComponents_s(label, children)
    for i in range(1, children.Length() + 1):
        _walk(shape_tool, children.Value(i), effective_name, loc, out, face_fn)


def _read_xcaf_document(path: str):
    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)

    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    status = reader.ReadFile(path)
    if status != IFSelect_RetDone:
        raise RuntimeError(f"failed to read STEP file: {path!r} (status={status})")
    if not reader.Transfer(doc):
        raise RuntimeError(f"failed to transfer STEP data into XCAF document: {path!r}")
    return doc


def _free_shape_labels(doc) -> tuple:
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    free_shapes = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free_shapes)
    return shape_tool, free_shapes


def parse_step_faces(path: str) -> dict[str, list[StepFace]]:
    """Parse a STEP file and return its faces grouped by CATIA PartNumber.

    Coordinates are in the STEP file's own units (mm, matching CATIA/the
    rest of this pipeline) and in the assembly's global frame (ancestor
    ``TopLoc_Location``s are composed and applied).
    """
    doc = _read_xcaf_document(path)
    shape_tool, free_shapes = _free_shape_labels(doc)

    faces: list[StepFace] = []
    for i in range(1, free_shapes.Length() + 1):
        _walk(shape_tool, free_shapes.Value(i), "", TopLoc_Location(), faces, _face_to_step_face)

    grouped: dict[str, list[StepFace]] = {}
    for f in faces:
        grouped.setdefault(f.part_name, []).append(f)
    return grouped


@dataclass
class MarkerSphere:
    """One weld-spot marker ball found in a STEP file (e.g. ``raw_data/component/SPOT.step``).

    ``label`` is the STEP/XCAF instance name the marker was found under —
    informational only (see ``parse_step_spheres`` docstring: it does not
    reliably correspond to real assembly PartNumbers, so it must not be used
    to key matching against ``faces.json``/``candidates.json``).
    """

    center: Vec3
    radius: float
    label: str = ""


# Weld-spot marker balls are exported as >=2 faces sharing one analytic
# sphere center (see parse_step_spheres docstring). On raw_data/component/SPOT.step the two
# hemisphere centers of the same marker agreed on X/Z to ~0.002mm and the
# sphere.Location() each hemisphere's adaptor reports is exactly identical
# (both derive from the same analytic sphere), so a generous-but-still-far-
# below-the-20mm-min-point-spacing tolerance is safe here.
_SPHERE_DEDUPE_TOL_MM = 0.5


def _sphere_face_or_none(face, part_name: str) -> MarkerSphere | None:
    adaptor = BRepAdaptor_Surface(face)
    if adaptor.GetType() != GeomAbs_Sphere:
        return None
    sphere = adaptor.Sphere()
    center = sphere.Location()
    return MarkerSphere(
        center=(float(center.X()), float(center.Y()), float(center.Z())),
        radius=float(sphere.Radius()),
        label=part_name,
    )


def parse_step_spheres(path: str, dedupe_tol_mm: float = _SPHERE_DEDUPE_TOL_MM) -> list[MarkerSphere]:
    """Parse a STEP file for spherical marker faces and return one entry per
    unique sphere, in the assembly's global frame.

    Built for ``raw_data/component/SPOT.step``: real weld-spot locations marked as small
    (r=3mm) ball geometry, one weld point per ball. Unlike ``parse_step_faces``'s
    vertex-plane-fit planarity check, sphere detection here uses OCCT's
    analytic surface type (``BRepAdaptor_Surface.GetType() ==
    GeomAbs_Sphere``) directly — reliable for this file (verified: all 572
    marker faces in ``SPOT.step`` are typed ``GeomAbs_Sphere``, each with
    ``radius == 3.0`` exactly), unlike the planar case where STEP export
    loses the ``GeomAbs_Plane`` type for real part geometry (see module
    docstring pitfall 3).

    Each ball is exported as 2 hemisphere faces (split by some plane through
    the center) rather than 1 closed spherical face — verified on
    ``SPOT.step``: 572 sphere faces collapse to exactly 286 unique centers,
    2 faces each, both hemisphere centroids equidistant from and colinear
    with the shared analytic center. Centers within ``dedupe_tol_mm`` of
    each other are merged (position/radius averaged) into one
    ``MarkerSphere``; this is a broad tolerance relative to the sub-mm
    agreement observed, but still far below the pipeline's 20mm minimum
    point spacing so it cannot merge two genuinely distinct weld points.
    """
    doc = _read_xcaf_document(path)
    shape_tool, free_shapes = _free_shape_labels(doc)

    raw: list[MarkerSphere] = []
    for i in range(1, free_shapes.Length() + 1):
        _walk(shape_tool, free_shapes.Value(i), "", TopLoc_Location(), raw, _sphere_face_or_none)

    clusters: list[list[MarkerSphere]] = []
    for sphere in raw:
        center = np.asarray(sphere.center, dtype=float)
        match = next(
            (
                c
                for c in clusters
                if np.linalg.norm(np.asarray(c[0].center, dtype=float) - center) <= dedupe_tol_mm
            ),
            None,
        )
        if match is None:
            clusters.append([sphere])
        else:
            match.append(sphere)

    merged: list[MarkerSphere] = []
    for cluster in clusters:
        centers = [s.center for s in cluster]
        radii = [s.radius for s in cluster]
        avg_center = tuple(sum(c[i] for c in centers) / len(centers) for i in range(3))
        avg_radius = sum(radii) / len(radii)
        merged.append(MarkerSphere(center=avg_center, radius=avg_radius, label=cluster[0].label))
    return merged
