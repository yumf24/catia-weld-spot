"""Build and validate a CAD-backed ANSA v24.1.1 component weld review scene."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.component_weld_ansa_scene import (  # noqa: E402
    ANSA_VERSION,
    LAYER_COLORS,
    LAYER_RGB,
    LINK_LAYER,
    MARKER_RADIUS_MM,
    SCENE_DATABASE,
    SCENE_DISPLAY_SCRIPT,
    SCENE_SCREENSHOTS,
    SCENE_STARTUP_SCRIPT,
    SPHERE_FACE_COUNT,
    load_scene_inputs,
    scene_paths,
)
from weld_core.data_layout import register_artifact, sha256_file  # noqa: E402
from check_ansa_weld_visualization import newest_completed_run, resolve_ansa_shortcut  # noqa: E402


def _display_script_source() -> str:
    """Return a non-blocking ANSA script that applies review display flags."""
    return '''"""Apply the intended shaded display for component_weld_cad_review.ansa."""
from ansa import base


def apply_review_display():
    base.SetViewButton({
        "VIEWMODE": "PART",
        "SHADOW": "on",
        "WIRE": "off",
        "CONS": "off",
        "BOUNDS": "off",
        "M.Pnt.": "off",
        "C.NODE": "off",
        "GRIDs": "off",
        "Hot Points": "off",
    })


def main():
    apply_review_display()
'''


def _startup_script_source(display_script_path: Path) -> str:
    """Return an ANSA GUI startup script for an already-open database."""
    return textwrap.dedent(
        """\
        \"\"\"Apply CAD weld review presentation settings to the open database.\"\"\"
        from ansa import base

        DISPLAY_SCRIPT_PATH = {display_script_path!r}

        def main():
            namespace = {{"__file__": DISPLAY_SCRIPT_PATH}}
            with open(DISPLAY_SCRIPT_PATH, encoding="utf-8") as handle:
                exec(compile(handle.read(), DISPLAY_SCRIPT_PATH, "exec"), namespace)
            namespace["apply_review_display"]()
        """
    ).format(display_script_path=str(display_script_path))


def _runner_source(run_dir: Path, cad_path: Path, analysis: dict[str, Any], expected_counts: dict[str, int]) -> str:
    paths = scene_paths(run_dir)
    marker_rows = {
        "TP_TRUTH": [row["ground_truth_position_mm"] for row in analysis["true_positives"]],
        "TP_CANDIDATE": [row["candidate_position_mm"] for row in analysis["true_positives"]],
        "FP_CANDIDATE": [row["candidate_position_mm"] for row in analysis["false_positives"]],
        "FN_TRUTH": [row["ground_truth_position_mm"] for row in analysis["false_negatives"]],
    }
    values = {
        "cad_path": str(cad_path),
        "database_path": str(paths["database"]),
        "result_path": str(run_dir / "ansa" / "component_weld_cad_review_runner.json"),
        "screenshots": {name: str(run_dir / path) for name, path in SCENE_SCREENSHOTS.items()},
        "display_script_path": str(paths["display_script"]),
        "marker_rows": marker_rows,
        "expected_counts": expected_counts,
        "colors": LAYER_RGB,
        "radius": MARKER_RADIUS_MM,
    }
    return textwrap.dedent(
        """\
        import json
        import os
        from ansa import base, constants, session, utils

        CAD_PATH = {cad_path!r}
        DATABASE_PATH = {database_path!r}
        RESULT_PATH = {result_path!r}
        SCREENSHOTS = {screenshots!r}
        DISPLAY_SCRIPT_PATH = {display_script_path!r}
        MARKER_ROWS = {marker_rows!r}
        EXPECTED_COUNTS = {expected_counts!r}
        COLORS = {colors!r}
        RADIUS_MM = {radius!r}

        def _named_set(name):
            group = base.CreateEntity(constants.NASTRAN, "SET", {{"Name": name}})
            if group is None:
                raise RuntimeError("could not create Set " + name)
            return group

        def _set_color(entity, rgb):
            # ANSA v24.1.1 stores custom ANSAPART display color in these card
            # fields rather than exposing a SetEntityColor helper.
            entity.set_entity_values(constants.NASTRAN, {{
                "Is Color Active": "YES", "COLOR_R": rgb[0], "COLOR_G": rgb[1],
                "COLOR_B": rgb[2], "TRANSPARENCY": 0,
            }})
            actual = entity.card_fields(constants.NASTRAN, True)
            if (actual.get("Is Color Active") != "YES" or
                    tuple(actual.get(key) for key in ("COLOR_R", "COLOR_G", "COLOR_B")) != tuple(rgb)):
                raise RuntimeError("ANSA could not apply requested marker color")

        def _add_spheres(name, positions):
            part = base.NewPart(name + "_MARKERS")
            if part is None:
                raise RuntimeError("could not create marker part " + name)
            _set_color(part, COLORS[name])
            # Keep one representative sphere in its own same-colour Part so
            # ANSA can create a reliable close-up proof using ZoomInEnt.
            detail_part = base.NewPart(name + "_DETAIL_MARKER")
            if detail_part is None:
                raise RuntimeError("could not create marker detail part " + name)
            _set_color(detail_part, COLORS[name])
            group = _named_set(name)
            faces = []
            for index, position in enumerate(positions):
                target_part = detail_part if index == 0 else part
                created = base.CreateVolumeSphere(position, RADIUS_MM, part=target_part, volumes=False)
                if not created:
                    raise RuntimeError("could not create marker sphere in " + name)
                faces.extend(created)
            base.AddToSet(group, faces)
            return group, faces, detail_part

        def _count_set(name):
            matches = [e for e in base.NameToEnts(name) if e.ansa_type(constants.NASTRAN) == "SET"]
            if len(matches) != 1:
                raise RuntimeError("expected exactly one Set " + name)
            return len(base.CollectEntities(constants.NASTRAN, matches[0], "FACE"))

        def _cad_face_count():
            return len(base.CollectEntities(constants.NASTRAN, None, "FACE"))

        def _set_review_display():
            namespace = {{"__file__": DISPLAY_SCRIPT_PATH}}
            with open(DISPLAY_SCRIPT_PATH, encoding="utf-8") as handle:
                exec(compile(handle.read(), DISPLAY_SCRIPT_PATH, "exec"), namespace)
            namespace["apply_review_display"]()

        def main():
            result = {{"cad_import_status": False, "save_status": None, "reopen_status": None, "expected_marker_counts": EXPECTED_COUNTS}}
            try:
                open_status = base.Open(CAD_PATH)
                if open_status != 0:
                    raise RuntimeError("component.step import returned %r" % (open_status,))
                result["cad_import_status"] = True
                result["cad_face_count_before_markers"] = _cad_face_count()
                if result["cad_face_count_before_markers"] < 1:
                    raise RuntimeError("component.step imported no CAD faces")
                marker_detail_parts = {{}}
                for name, positions in MARKER_ROWS.items():
                    _group, _marker_faces, marker_detail_parts[name] = _add_spheres(name, positions)
                # Keep matching information as an empty, disabled Set in this
                # review scene. It is traceable to the source CSV but does not
                # draw links or create FE entities by default.
                _named_set("MATCH_LINK")
                result["created_marker_face_counts"] = {{name: _count_set(name) for name in MARKER_ROWS}}
                _set_review_display()
                # This happens before SaveAs because ANSA invalidates in-memory
                # Part references when it subsequently reopens the database.
                base.SetViewAngles("F10")
                base.ZoomInEnt(marker_detail_parts["TP_TRUTH"])
                utils.SnapShot(SCREENSHOTS["marker_detail"], "PNG")
                base.ZoomAll()
                result["save_status"] = base.SaveAs(DATABASE_PATH, silent=True)
                if result["save_status"] not in (None, 0):
                    raise RuntimeError("SaveAs returned %r" % (result["save_status"],))
                result["reopen_status"] = base.Open(DATABASE_PATH)
                if result["reopen_status"] != 0:
                    raise RuntimeError("Open returned %r" % (result["reopen_status"],))
                result["reopened_marker_face_counts"] = {{name: _count_set(name) for name in MARKER_ROWS}}
                _set_review_display()
                for key, view in (("isometric", "F10"), ("front", "F1"), ("right", "F2"), ("top", "F3")):
                    base.SetViewAngles(view)
                    base.ZoomAll()
                    utils.SnapShot(SCREENSHOTS[key], "PNG")
                base.SetViewAngles("F10")
                base.ZoomAll()
                result["screenshot_paths"] = SCREENSHOTS
                result["database_path"] = DATABASE_PATH
                result["pass"] = (result["created_marker_face_counts"] == EXPECTED_COUNTS and result["reopened_marker_face_counts"] == EXPECTED_COUNTS)
            except Exception as exc:
                result["error"] = repr(exc)
                result["pass"] = False
            with open(RESULT_PATH, "w") as handle:
                json.dump(result, handle, indent=2)
            if not result["pass"]:
                raise RuntimeError(result.get("error", "ANSA CAD scene build failed"))
            session.Quit(0)
        """
    ).format(**values)


def _write_failure(run_dir: Path, message: str) -> None:
    # A partial database must never be mistaken for a published review scene.
    # The validation report and ANSA log remain available for diagnosis.
    scene_paths(run_dir)["database"].unlink(missing_ok=True)
    path = run_dir / "ansa_cad_scene_validation.json"
    path.write_text(json.dumps({"format_version": 1, "pass": False, "error": message}, indent=2) + "\n", encoding="utf-8")


def _run(executable: Path, run_dir: Path, inputs: dict[str, Any], timeout_minutes: int) -> dict[str, Any]:
    ansa_dir = run_dir / "ansa"
    (ansa_dir / "views").mkdir(parents=True, exist_ok=True)
    paths = scene_paths(run_dir)
    paths["display_script"].write_text(_display_script_source(), encoding="utf-8")
    paths["startup_script"].write_text(
        _startup_script_source(paths["display_script"]), encoding="utf-8"
    )
    runner = ansa_dir / "build_component_weld_cad_review.py"
    expected_face_counts = {name: count * SPHERE_FACE_COUNT for name, count in inputs["marker_counts"].items() if name != LINK_LAYER}
    runner.write_text(_runner_source(run_dir, inputs["cad_path"], inputs["analysis"], expected_face_counts), encoding="utf-8")
    result_path = ansa_dir / "component_weld_cad_review_runner.json"
    result_path.unlink(missing_ok=True)
    command = [str(executable), "-exec", f"load_script:{runner}", "-exec", "main"]
    completed = subprocess.run(command, cwd=run_dir, capture_output=True, text=True, timeout=timeout_minutes * 60)
    log_path = scene_paths(run_dir)["log"]
    log_path.write_text("command: " + subprocess.list2cmdline(command) + "\n\nstdout:\n" + completed.stdout + "\n\nstderr:\n" + completed.stderr, encoding="utf-8")
    if not result_path.is_file():
        raise ValueError(f"ANSA did not write a scene result (exit {completed.returncode}); see {log_path}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["process_exit_code"] = completed.returncode
    result["log_path"] = str(log_path.relative_to(run_dir)).replace("\\", "/")
    return result


def _validate(run_dir: Path, result: dict[str, Any], inputs: dict[str, Any]) -> None:
    if not result.get("pass") or result.get("process_exit_code") != 0 or not result.get("cad_import_status"):
        raise ValueError(result.get("error", "ANSA CAD scene failed"))
    if result.get("cad_face_count_before_markers", 0) < 1:
        raise ValueError("ANSA scene contains no imported CAD faces")
    expected = {name: count * SPHERE_FACE_COUNT for name, count in inputs["marker_counts"].items() if name != LINK_LAYER}
    for key in ("created_marker_face_counts", "reopened_marker_face_counts"):
        if result.get(key) != expected:
            raise ValueError(f"{key} does not match expected sphere face counts")
    paths = scene_paths(run_dir)
    for path in [paths["database"], paths["display_script"], paths["startup_script"], *[run_dir / value for value in SCENE_SCREENSHOTS.values()]]:
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"missing or empty ANSA scene artifact: {path}")


def _publish(run_dir: Path, executable: Path, result: dict[str, Any], inputs: dict[str, Any]) -> None:
    paths = scene_paths(run_dir)
    validation = {
        "format_version": 1,
        "pass": True,
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ansa_version": ANSA_VERSION,
        "ansa_executable": str(executable),
        "cad_source": "raw_data/component/component.step",
        "cad_face_count": result["cad_face_count_before_markers"],
        "marker_shape": "cad_sphere",
        "marker_radius_mm": MARKER_RADIUS_MM,
        "sphere_face_count": SPHERE_FACE_COUNT,
        "layer_colors": LAYER_COLORS,
        "default_visible_layers": list(LAYER_COLORS),
        "default_hidden_layers": [LINK_LAYER],
        "expected_marker_rows": inputs["marker_counts"],
        "expected_marker_face_counts": {name: count * SPHERE_FACE_COUNT for name, count in inputs["marker_counts"].items() if name != LINK_LAYER},
        "created_marker_face_counts": result["created_marker_face_counts"],
        "reopened_marker_face_counts": result["reopened_marker_face_counts"],
        "database_path": SCENE_DATABASE,
        "display_script_path": SCENE_DISPLAY_SCRIPT,
        "startup_script_path": SCENE_STARTUP_SCRIPT,
        "screenshot_paths": SCENE_SCREENSHOTS,
        "log_path": result["log_path"],
        "marker_semantics": "visual_markers_not_fe_spotwelds",
    }
    paths["validation"].write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    paths["report"].write_text(
        "# ANSA CAD weld review scene\n\n"
        f"- ANSA v{ANSA_VERSION}: CAD import, marker creation, save/reopen and four screenshots passed.\n"
        f"- Imported CAD faces: {validation['cad_face_count']}.\n"
        f"- Marker spheres: radius {MARKER_RADIUS_MM:g} mm; TP truth/candidate green, FP red, FN yellow.\n"
        "- MATCH_LINK is traceable but hidden by default. No FE mesh, connector, element, or SPOTWELD was created.\n"
        "- To open with shaded markers in a fresh ANSA session, run ansa/open_component_weld_cad_review.py.\n",
        encoding="utf-8",
    )
    for name, path, kind in (("ansa_cad_scene_validation", paths["validation"], "json"), ("ansa_cad_scene_report", paths["report"], "markdown"), ("ansa_cad_scene_database", paths["database"], "ansa_database"), ("ansa_cad_scene_display_script", paths["display_script"], "python"), ("ansa_cad_scene_startup_script", paths["startup_script"], "python"), ("ansa_cad_scene_log", paths["log"], "log")):
        register_artifact(run_dir, name, path, kind=kind, sha256=sha256_file(path))
    for view, relative in SCENE_SCREENSHOTS.items():
        path = run_dir / relative
        register_artifact(run_dir, f"ansa_cad_scene_{view}", path, kind="png", sha256=sha256_file(path))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest-run", action="store_true")
    group.add_argument("--run-dir", type=Path)
    parser.add_argument("--timeout-minutes", type=int, default=30)
    args = parser.parse_args(argv)
    run_dir = newest_completed_run() if args.latest_run else args.run_dir.resolve()
    try:
        if args.timeout_minutes <= 0:
            raise ValueError("--timeout-minutes must be a positive integer")
        inputs = load_scene_inputs(run_dir, REPO_ROOT)
        executable = resolve_ansa_shortcut()
        result = _run(executable, run_dir, inputs, args.timeout_minutes)
        _validate(run_dir, result, inputs)
        _publish(run_dir, executable, result, inputs)
    except (OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        _write_failure(run_dir, str(exc))
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] ANSA CAD weld review scene -> {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
