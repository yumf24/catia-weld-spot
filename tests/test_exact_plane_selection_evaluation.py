from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.gp import gp_Pln, gp_Pnt, gp_Dir

from weld_core.exact_plane_selection_evaluation import evaluate_plane_selection
from weld_core.plane_reference_labels import IndexedStepFace
from weld_core.step_geometry import StepFace


def _face(index: int, x0=0.0, x1=10.0, *, z=0.0, normal=(0.0, 0.0, 1.0)):
    shape = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, z), gp_Dir(*normal)), x0, x1, 0, 10).Face()
    return IndexedStepFace("P", index, StepFace(
        "P", centroid=((x0 + x1) / 2, 5, z), normal=normal, area=(x1 - x0) * 10,
        is_planar=True, shape=shape,
    ))


def test_exact_metrics_use_single_face_coverage():
    result = evaluate_plane_selection([_face(1), _face(2, 20, 30)], [_face(7), _face(8, 40, 50)])
    assert result["summary"] == {"selected_faces": 2, "reference_faces": 2, "true_positives": 1,
        "false_positives": 1, "false_negatives": 1, "precision": 0.5, "recall": 0.5, "passed": False}
    assert result["reference_faces"][1]["status"] == "unmatched"


def test_95_percent_coverage_is_a_match_but_angle_and_distance_are_not():
    covered = evaluate_plane_selection([_face(1)], [_face(7, 0, 9.5)])
    angled = evaluate_plane_selection([_face(1)], [_face(7, normal=(0.01, 0, 1))])
    distant = evaluate_plane_selection([_face(1)], [_face(7, z=0.06)])
    assert covered["summary"]["recall"] == 1.0
    assert angled["summary"]["false_negatives"] == 1
    assert distant["summary"]["false_negatives"] == 1
