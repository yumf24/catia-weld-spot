"""step_geometry tests -- require OCP (part of the cadquery dependency).

Uses shapes built directly in memory via OCP's BRep primitives rather than
the large STEP fixtures under data/ (those are real CAD exports, gitignored,
and not something CI/unit tests should depend on).
"""

from __future__ import annotations

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
