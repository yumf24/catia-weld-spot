"""step_geometry tests -- require OCP (part of the cadquery dependency).

Uses shapes built directly in memory via OCP's BRep primitives rather than
the large STEP fixtures under data/ (those are real CAD exports, gitignored,
and not something CI/unit tests should depend on).
"""

from __future__ import annotations

from pathlib import Path

import pytest

OCP = pytest.importorskip("OCP")

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeSphere  # noqa: E402
from OCP.TopAbs import TopAbs_FACE  # noqa: E402
from OCP.TopExp import TopExp_Explorer  # noqa: E402
from OCP.TopoDS import TopoDS  # noqa: E402

from weld_core import step_geometry as sg  # noqa: E402


def _faces_of(shape):
    faces = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        faces.append(TopoDS.Face_s(exp.Current()))
        exp.Next()
    return faces


def test_box_faces_are_planar_with_four_deduped_vertices():
    box = BRepPrimAPI_MakeBox(10.0, 20.0, 30.0).Shape()
    faces = _faces_of(box)
    assert len(faces) == 6

    step_faces = [sg._face_to_step_face(f, "TESTBOX") for f in faces]
    areas = sorted(f.area for f in step_faces)
    assert areas == pytest.approx(sorted([200.0, 200.0, 300.0, 300.0, 600.0, 600.0]))

    for f in step_faces:
        assert len(f.vertices) == 4
        assert f.is_planar is True
        assert f.max_residual < sg.PLANAR_RESIDUAL_TOL_MM


def test_sphere_faces_are_not_planar():
    sphere = BRepPrimAPI_MakeSphere(5.0).Shape()
    faces = _faces_of(sphere)
    assert len(faces) >= 1

    step_faces = [sg._face_to_step_face(f, "TESTSPHERE") for f in faces]
    assert all(not f.is_planar for f in step_faces)


def test_parse_step_faces_groups_by_part_name(tmp_path):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

    box = BRepPrimAPI_MakeBox(10.0, 20.0, 30.0).Shape()
    step_path = tmp_path / "box.step"
    writer = STEPControl_Writer()
    writer.Transfer(box, STEPControl_AsIs)
    writer.Write(str(step_path))

    grouped = sg.parse_step_faces(str(step_path))
    all_faces = [f for faces in grouped.values() for f in faces]
    assert len(all_faces) == 6
    assert all(f.is_planar for f in all_faces)


def test_parse_step_spheres_merges_two_marker_balls_into_two_points(tmp_path):
    """Mirrors raw_data/component/SPOT.step's shape: two marker balls.

    A single BRepPrimAPI_MakeSphere shape is already one solid (its faces
    all share one analytic center), so two spheres at different locations
    stand in for "two distinct weld points" -- parse_step_spheres must
    return exactly one merged MarkerSphere per location, not one per face.
    """
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
    from OCP.gp import gp_Trsf, gp_Vec
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.TopoDS import TopoDS_Compound
    from OCP.BRep import BRep_Builder

    sphere_a = BRepPrimAPI_MakeSphere(3.0).Shape()
    trsf = gp_Trsf()
    trsf.SetTranslation(gp_Vec(100.0, 0.0, 0.0))
    sphere_b = BRepBuilderAPI_Transform(sphere_a, trsf, True).Shape()

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    builder.Add(compound, sphere_a)
    builder.Add(compound, sphere_b)

    step_path = tmp_path / "spots.step"
    writer = STEPControl_Writer()
    writer.Transfer(compound, STEPControl_AsIs)
    writer.Write(str(step_path))

    spheres = sg.parse_step_spheres(str(step_path))

    assert len(spheres) == 2
    centers = sorted(s.center for s in spheres)
    assert centers[0] == pytest.approx((0.0, 0.0, 0.0), abs=1e-6)
    assert centers[1] == pytest.approx((100.0, 0.0, 0.0), abs=1e-6)
    assert all(s.radius == pytest.approx(3.0) for s in spheres)


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "raw_data" / "component-simplify" / "component_simplify.step").is_file(),
    reason="local component-simplify validation assets are gitignored",
)
def test_component_simplify_reference_step_is_a_stable_planarity_fixture():
    """Validate that the registered small-part/reference STEP pair is intact."""
    root = Path(__file__).resolve().parents[1] / "raw_data" / "component-simplify"
    model = sg.parse_step_faces(str(root / "component_simplify.step"))
    reference = sg.parse_step_faces(str(root / "component_simplify_surface.step"))
    model_faces = [face for faces in model.values() for face in faces]
    reference_faces = [face for faces in reference.values() for face in faces]

    assert len(model_faces) == 2834
    assert sum(face.is_planar for face in model_faces) == 525
    assert len(reference_faces) == 89
    assert sum(face.is_planar for face in reference_faces) == 40
