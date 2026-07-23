"""Run or verify the real ANSA visual-marker validation for a component run.

The generated ANSA runner deliberately creates only GRID display markers and
Sets.  It never creates connectors, elements, or SPOTWELD entities.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.data_layout import register_artifact, sha256_file  # noqa: E402


ANSA_VERSION = "24.1.1"
RUN_ROOT = REPO_ROOT / "data" / "component-weld-evaluation"
SHORTCUT = Path(
    r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\BETA CAE Systems"
    r"\ANSA 24.1.1\ANSA v24.1.1.lnk"
)
VALIDATION_FILE = "ansa_render_validation.json"
EXPECTED_LAYERS = ("TP_TRUTH", "TP_CANDIDATE", "FP_CANDIDATE", "FN_TRUTH", "MATCH_LINK")


def newest_completed_run(run_root: Path = RUN_ROOT) -> Path:
    runs = [
        path
        for path in run_root.iterdir()
        if path.is_dir()
        and (path / "manifest.json").is_file()
        and json.loads((path / "manifest.json").read_text(encoding="utf-8")).get("status") == "completed"
    ]
    if not runs:
        raise ValueError(f"no completed component evaluation run under {run_root}")
    return max(runs, key=lambda path: path.name)


def resolve_ansa_shortcut(shortcut: Path = SHORTCUT) -> Path:
    """Resolve the installed v24.1.1 Start-menu shortcut without hard-coding its target."""
    if not shortcut.is_file():
        raise ValueError(f"ANSA v{ANSA_VERSION} shortcut was not found: {shortcut}")
    try:
        shell = __import__("win32com.client", fromlist=["Dispatch"]).Dispatch("WScript.Shell")
        target = Path(shell.CreateShortcut(str(shortcut)).TargetPath)
    except Exception as exc:  # pragma: no cover - Windows integration only
        raise ValueError(f"could not resolve ANSA shortcut {shortcut}: {exc}") from exc
    if not target.is_file() or "ansa_v24.1.1" not in str(target).lower():
        raise ValueError(f"shortcut does not resolve to ANSA v{ANSA_VERSION}: {target}")
    return target


def expected_counts(run_dir: Path) -> dict[str, int]:
    manifest = json.loads((run_dir / "ansa_import_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("required_ansa_version") != ANSA_VERSION:
        raise ValueError("ANSA import manifest does not require v24.1.1")
    counts = {name: int(manifest["layers"][name]["count"]) for name in EXPECTED_LAYERS}
    if any(count < 1 for count in counts.values()):
        raise ValueError("ANSA marker package has an empty required layer")
    return counts


def expected_grid_counts(marker_rows: dict[str, int]) -> dict[str, int]:
    """MATCH_LINK has two visual GRID endpoints for every CSV link row."""
    return {name: count * 2 if name == "MATCH_LINK" else count for name, count in marker_rows.items()}


def _runner_source(run_dir: Path, counts: dict[str, int]) -> str:
    """Return a self-contained script loaded by ANSA's ``-exec load_script``."""
    ansa_dir = run_dir / "ansa"
    values = {
        "import_path": str(ansa_dir / "ansa_import.py"),
        "database_path": str(ansa_dir / "component_weld_visualization.ansa"),
        "screenshot_path": str(ansa_dir / "component_weld_visualization.png"),
        "result_path": str(ansa_dir / "ansa_runner_result.json"),
        "expected_counts": counts,
    }
    return textwrap.dedent(
        """\
        import importlib.util
        import json
        import os
        from ansa import base, constants, session, utils

        IMPORT_PATH = {import_path!r}
        DATABASE_PATH = {database_path!r}
        SCREENSHOT_PATH = {screenshot_path!r}
        RESULT_PATH = {result_path!r}
        EXPECTED_COUNTS = {expected_counts!r}

        def _set_by_name(name):
            entities = base.NameToEnts(name)
            matches = [entity for entity in entities if entity.ansa_type(constants.NASTRAN) == "SET"]
            if len(matches) != 1:
                raise RuntimeError("expected one SET named %s, found %d" % (name, len(matches)))
            return matches[0]

        def _counts():
            return {{name: len(base.CollectEntities(constants.NASTRAN, _set_by_name(name), "GRID")) for name in EXPECTED_COUNTS}}

        def main():
            result = {{"import_status": False, "save_status": None, "reopen_status": None, "expected_counts": EXPECTED_COUNTS}}
            try:
                spec = importlib.util.spec_from_file_location("component_ansa_import", IMPORT_PATH)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.main()
                result["import_status"] = True
                result["created_entity_counts"] = _counts()
                result["save_status"] = base.SaveAs(DATABASE_PATH, silent=True)
                if result["save_status"] not in (None, 0):
                    raise RuntimeError("SaveAs returned %r" % (result["save_status"],))
                result["reopen_status"] = base.Open(DATABASE_PATH)
                if result["reopen_status"] != 0:
                    raise RuntimeError("Open returned %r" % (result["reopen_status"],))
                result["reopened_entity_counts"] = _counts()
                base.SetEntityVisibilityValues(constants.NASTRAN, {{"GRID": "enable"}})
                base.SetViewAngles("F1")
                base.ZoomAll()
                utils.SnapShot(SCREENSHOT_PATH, "PNG")
                result["screenshot_path"] = SCREENSHOT_PATH
                result["database_path"] = DATABASE_PATH
                result["pass"] = result["created_entity_counts"] == EXPECTED_COUNTS and result["reopened_entity_counts"] == EXPECTED_COUNTS
            except Exception as exc:
                result["error"] = repr(exc)
                result["pass"] = False
            with open(RESULT_PATH, "w") as handle:
                json.dump(result, handle, indent=2)
            if not result["pass"]:
                raise RuntimeError(result.get("error", "ANSA validation failed"))
            # Run with ANSA's real GUI renderer (rather than -nogui) so the
            # captured PNG proves an actual drawable viewport, then exit only
            # after the database and result evidence are safely on disk.
            session.Quit(0)
        """
    ).format(**values)


def _run_ansa(executable: Path, run_dir: Path, counts: dict[str, int], timeout_seconds: int) -> dict[str, Any]:
    ansa_dir = run_dir / "ansa"
    runner = ansa_dir / "ansa_validation_runner.py"
    runner.write_text(_runner_source(run_dir, counts), encoding="utf-8")
    result_path = ansa_dir / "ansa_runner_result.json"
    result_path.unlink(missing_ok=True)
    log_path = ansa_dir / "ansa_render_validation.log"
    command = [str(executable), "-exec", f"load_script:{runner}", "-exec", "main"]
    completed = subprocess.run(
        command,
        cwd=run_dir,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )
    log_path.write_text(
        "command: " + subprocess.list2cmdline(command) + "\n\nstdout:\n" + completed.stdout + "\n\nstderr:\n" + completed.stderr,
        encoding="utf-8",
    )
    if not result_path.is_file():
        raise ValueError(f"ANSA did not write a validation result (exit {completed.returncode}); see {log_path}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["process_exit_code"] = completed.returncode
    result["log_path"] = str(log_path.relative_to(run_dir)).replace("\\", "/")
    return result


def _validate_result(run_dir: Path, result: dict[str, Any], counts: dict[str, int]) -> None:
    if not result.get("pass") or result.get("process_exit_code") not in (None, 0):
        raise ValueError(f"ANSA import/reopen failed: {result.get('error', 'unknown error')}")
    for key in ("created_entity_counts", "reopened_entity_counts"):
        if result.get(key) != counts:
            raise ValueError(f"{key} does not equal manifest layer counts")
    for field in ("database_path", "screenshot_path"):
        path = Path(result.get(field, ""))
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"ANSA produced no nonempty {field}: {path}")


def _write_reports(run_dir: Path, executable: Path, result: dict[str, Any], marker_rows: dict[str, int]) -> None:
    evaluation = json.loads((run_dir / "weld_point_evaluation.json").read_text(encoding="utf-8"))
    validation = {
        "format_version": 1,
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ansa_version": ANSA_VERSION,
        "ansa_executable": str(executable),
        "marker_semantics": "visual_markers_not_fe_spotwelds",
        "import_status": result["import_status"],
        "save_status": result["save_status"],
        "reopen_status": result["reopen_status"],
        "expected_marker_rows": marker_rows,
        "expected_entity_counts": expected_grid_counts(marker_rows),
        "created_entity_counts": result["created_entity_counts"],
        "reopened_entity_counts": result["reopened_entity_counts"],
        "database_path": str(Path(result["database_path"]).relative_to(run_dir)).replace("\\", "/"),
        "screenshot_path": str(Path(result["screenshot_path"]).relative_to(run_dir)).replace("\\", "/"),
        "log_path": result["log_path"],
        "pass": True,
    }
    (run_dir / VALIDATION_FILE).write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# ANSA render validation",
        "",
        f"- ANSA: v{ANSA_VERSION}",
        "- Import, save, reopen, count checks, and PNG render: **passed**.",
        f"- CSV marker rows: {', '.join(f'{name}={count}' for name, count in marker_rows.items())}.",
        f"- Created GRIDs: {', '.join(f'{name}={count}' for name, count in expected_grid_counts(marker_rows).items())}; MATCH_LINK has two endpoint GRIDs per link.",
        "- Markers are visual only; no FE connector, element, or SPOTWELD was created.",
    ]
    (run_dir / "ansa_render_validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = evaluation["summary"]
    conclusion = {
        "format_version": 1,
        "scope": "component_single_dataset_weld_point_evaluation",
        "evaluation_summary": summary,
        "ansa_render_validation": VALIDATION_FILE,
        "conclusion": "The component candidate run was successfully visualized in ANSA v24.1.1 as traceable visual markers.",
        "generalization_boundary": "This is single-dataset component evidence only and must not be presented as cross-part generalization.",
        "fe_spotweld_claim": False,
    }
    (run_dir / "component_weld_evaluation_conclusion.json").write_text(json.dumps(conclusion, indent=2) + "\n", encoding="utf-8")
    (run_dir / "component_weld_evaluation_conclusion.md").write_text(
        "# Component weld evaluation conclusion\n\n"
        f"ANSA v{ANSA_VERSION} import/save/reopen/render validation passed. At 10 mm, "
        f"TP/FP/FN = {summary['true_positives']}/{summary['false_positives']}/{summary['false_negatives']}; "
        f"precision = {summary['precision']:.2%}, recall = {summary['recall']:.2%}, F1 = {summary['f1']:.2%}.\n\n"
        "This is single-dataset component evidence only; it does not demonstrate cross-part generalization. "
        "ANSA entities are visual markers only, not FE SPOTWELD connectors.\n",
        encoding="utf-8",
    )
    for name, filename, kind in (
        ("ansa_render_validation", VALIDATION_FILE, "json"),
        ("ansa_render_validation_report", "ansa_render_validation.md", "markdown"),
        ("ansa_render_database", "ansa/component_weld_visualization.ansa", "ansa_database"),
        ("ansa_render_screenshot", "ansa/component_weld_visualization.png", "png"),
        ("ansa_render_log", result["log_path"], "log"),
        ("component_weld_evaluation_conclusion", "component_weld_evaluation_conclusion.json", "json"),
        ("component_weld_evaluation_conclusion_report", "component_weld_evaluation_conclusion.md", "markdown"),
    ):
        path = run_dir / filename
        register_artifact(run_dir, name, path, kind=kind, sha256=sha256_file(path))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest-run", action="store_true")
    group.add_argument("--run-dir", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--verify-only", action="store_true", help="validate existing evidence without starting ANSA")
    parser.add_argument("--force", action="store_true", help="rerun ANSA even when validation evidence already exists")
    args = parser.parse_args(argv)
    try:
        run_dir = newest_completed_run() if args.latest_run else args.run_dir.resolve()
        marker_rows = expected_counts(run_dir)
        counts = expected_grid_counts(marker_rows)
        existing = run_dir / VALIDATION_FILE
        if args.verify_only or (existing.is_file() and not args.force):
            validation = json.loads(existing.read_text(encoding="utf-8"))
            result = {**validation, "process_exit_code": 0}
            result["database_path"] = str(run_dir / validation["database_path"])
            result["screenshot_path"] = str(run_dir / validation["screenshot_path"])
            _validate_result(run_dir, result, counts)
        else:
            executable = resolve_ansa_shortcut()
            result = _run_ansa(executable, run_dir, counts, args.timeout_seconds)
            _validate_result(run_dir, result, counts)
            _write_reports(run_dir, executable, result, marker_rows)
    except (OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] ANSA v{ANSA_VERSION} visual-marker validation -> {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
