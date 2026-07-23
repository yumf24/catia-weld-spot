"""Build path-independent ANSA review packages for offline handoff."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Mapping

from .data_layout import sha256_file


PACKAGE_NAME = "component_weld_ansa_review"
DATABASE_RELATIVE_PATH = Path("ansa") / "component_weld_cad_review.ansa"
DISPLAY_SCRIPT_RELATIVE_PATH = Path("ANSA_TRANSL.py")
MANUAL_DISPLAY_RELATIVE_PATH = Path("ansa") / "apply_component_weld_review_display.py"
REMOTE_LAUNCHER_NAME = "open_component_weld_review.py"
PREVIEWS_RELATIVE_DIR = Path("previews")
README_NAME = "README.txt"
MANIFEST_NAME = "portable_review_manifest.json"
LAUNCHER_NAME = "open_component_weld_review.bat"


def display_script_source() -> str:
    """Return a portable ANSA startup/display script with no absolute paths."""
    return '''"""Shaded, topology-free display for the component weld review."""
import os

from ansa import base, guitk, utils


_snapshot_written = False


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


def _apply_after_database_load(_data=None):
    global _snapshot_written
    apply_review_display()
    probe_path = os.environ.get("COMPONENT_WELD_CAPTURE_STARTUP_DISPLAY")
    if probe_path and not _snapshot_written:
        utils.SnapShot(probe_path, "PNG")
        _snapshot_written = True
    return 0


# ANSA loads ANSA_TRANSL.py before it finishes restoring the database and its
# local Drawing Styles. Queue two post-event-loop applications so the final
# interactive view keeps Part colours and no topology overlays.
guitk.BCTimerSingleShot(3000, _apply_after_database_load, None)
guitk.BCTimerSingleShot(10000, _apply_after_database_load, None)
'''


def launcher_source() -> str:
    """Return a Windows launcher for the portable Listener-mode opener."""
    return r'''@echo off
setlocal EnableExtensions
set "PACKAGE_ROOT=%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%PACKAGE_ROOT%open_component_weld_review.py" %*
    exit /b %ERRORLEVEL%
)
where python >nul 2>&1
if not errorlevel 1 (
    python "%PACKAGE_ROOT%open_component_weld_review.py" %*
    exit /b %ERRORLEVEL%
)
echo [FAIL] Python 3 was not found. Install Python 3, then run this launcher again.
exit /b 1
'''


def remote_launcher_source() -> str:
    """Return a self-contained Python client for ANSA Listener Mode.

    ANSA restores Drawing Styles after a normal database open, so a startup
    script cannot reliably retain marker colours.  Listener Mode opens the
    scene and applies the view only after that restoration has completed.
    """
    return r'''"""Open this portable ANSA review with its intended display settings."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


PACKAGE_ROOT = Path(__file__).resolve().parent
DATABASE = PACKAGE_ROOT / "ansa" / "component_weld_cad_review.ansa"
DEFAULT_ANSA_ROOT = Path(r"C:\Program Files (x86)\BETA_CAE_Systems")


def find_ansa_executable(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("ANSA_EXECUTABLE"):
        candidates.append(Path(os.environ["ANSA_EXECUTABLE"]))
    candidates.extend(sorted(DEFAULT_ANSA_ROOT.glob("ansa_v*/ansa64.bat"), reverse=True))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "ANSA executable was not found. Set ANSA_EXECUTABLE or pass "
        "--ansa-executable C:\\path\\to\\ansa64.bat."
    )


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def remote_script(database: Path, verification_png: Path) -> str:
    return """from ansa import base, utils
database = {database!r}
verification_png = {verification_png!r}
if base.Open(database) != 0:
    raise RuntimeError("ANSA could not open portable review database: " + database)
base.SetViewButton({{
    "VIEWMODE": "PART", "SHADOW": "on", "WIRE": "off", "CONS": "off",
    "BOUNDS": "off", "M.Pnt.": "off", "C.NODE": "off", "GRIDs": "off",
    "Hot Points": "off",
}})
utils.SnapShot(verification_png, "PNG")
""".format(database=str(database), verification_png=str(verification_png))


def open_review(ansa_executable: Path, timeout_seconds: float) -> None:
    if not DATABASE.is_file():
        raise FileNotFoundError("portable review database is missing: " + str(DATABASE))
    port = free_port()
    remote_module = ansa_executable.parent / "scripts" / "RemoteControl" / "ansa"
    if not remote_module.is_dir():
        raise FileNotFoundError("ANSA Listener client module is missing: " + str(remote_module))
    sys.path.insert(0, str(remote_module))
    from AnsaProcessModule import IAPConnection, PostConnectionAction

    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(ansa_executable), "-listenport", str(port)], creationflags=creationflags)
    deadline = time.monotonic() + timeout_seconds
    connection = None
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            connection = IAPConnection(port)
            response = connection.hello()
            if not response.success():
                raise RuntimeError("ANSA Listener handshake failed")
            response = connection.run_script_text(
                remote_script(DATABASE.resolve(), PACKAGE_ROOT / "startup_display_verification.png")
            )
            # ANSA 24.1.1 returns no execution-details TLV for a successful
            # text script, whereas some builds return the explicit 0 code.
            if not response.success() or response.get_script_execution_details() not in (None, 0):
                raise RuntimeError("ANSA rejected the display script")
            connection.goodbye(PostConnectionAction.keep_listening)
            print("[OK] ANSA opened with Part-colour shaded CAD spheres.")
            print("[OK] display verification: " + str(PACKAGE_ROOT / "startup_display_verification.png"))
            return
        except Exception as exc:
            last_error = exc
            if connection is not None:
                try:
                    connection.close()
                except OSError:
                    pass
            time.sleep(1)
    raise RuntimeError("ANSA did not become ready before timeout") from last_error


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ansa-executable", help="path to ANSA ansa64.bat")
    parser.add_argument("--timeout", type=float, default=90.0, help="ANSA startup timeout in seconds")
    args = parser.parse_args(argv)
    try:
        open_review(find_ansa_executable(args.ansa_executable), args.timeout)
    except (OSError, RuntimeError, ValueError) as exc:
        print("[FAIL] " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''


def readme_source() -> str:
    return """Component weld ANSA review package

Open `open_component_weld_review.bat` on Windows. It uses the local .ansa file
association and leaves ANSA interactive. The package has no repository-specific
paths. It requires Python 3 (the standard Windows `py -3` launcher is used) and
an installed ANSA v24.1.1 or later. If ANSA is installed elsewhere, run
`open_component_weld_review.bat --ansa-executable C:\\path\\to\\ansa64.bat`.

The launcher uses ANSA Listener Mode to open the database and then applies its
Part-colour shaded display. This happens after ANSA has restored user Drawing
Styles, so CAD and 3 mm CAD weld markers render as round green/red/yellow spheres
rather than grey topology crosses. It writes `startup_display_verification.png`
beside the launcher as proof of the applied display. `ANSA_TRANSL.py` remains a
manual fallback script; it does not modify the recipient's ANSA profile.

The model contains visual CAD spheres only; it does not contain FE SPOTWELD,
connectors or FE elements.
"""


def build_portable_review(
    database_path: Path,
    output_dir: Path,
    *,
    preview_paths: Mapping[str, Path] | None = None,
    archive: bool = True,
) -> dict[str, Path]:
    """Copy a scene into an independent package and optionally ZIP it."""
    database_path = database_path.resolve()
    output_dir = output_dir.resolve()
    package_dir = output_dir / PACKAGE_NAME
    if not database_path.is_file():
        raise ValueError(f"missing ANSA database: {database_path}")
    if package_dir.exists():
        raise ValueError(f"portable package directory already exists: {package_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    database_destination = package_dir / DATABASE_RELATIVE_PATH
    database_destination.parent.mkdir(parents=True)
    shutil.copy2(database_path, database_destination)
    display_source = display_script_source()
    (package_dir / DISPLAY_SCRIPT_RELATIVE_PATH).write_text(display_source, encoding="utf-8")
    (package_dir / MANUAL_DISPLAY_RELATIVE_PATH).write_text(display_source, encoding="utf-8")
    (package_dir / REMOTE_LAUNCHER_NAME).write_text(remote_launcher_source(), encoding="utf-8")
    (package_dir / LAUNCHER_NAME).write_text(launcher_source(), encoding="utf-8", newline="\r\n")
    (package_dir / README_NAME).write_text(readme_source(), encoding="utf-8")
    preview_relatives: dict[str, str] = {}
    for name, source_path in (preview_paths or {}).items():
        source_path = source_path.resolve()
        if not source_path.is_file():
            raise ValueError(f"missing ANSA preview image: {source_path}")
        destination = package_dir / PREVIEWS_RELATIVE_DIR / source_path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        preview_relatives[name] = destination.relative_to(package_dir).as_posix()
    manifest = {
        "format_version": 1,
        "database": DATABASE_RELATIVE_PATH.as_posix(),
        "database_sha256": sha256_file(database_destination),
        "display_startup_script": DISPLAY_SCRIPT_RELATIVE_PATH.as_posix(),
        "manual_display_script": MANUAL_DISPLAY_RELATIVE_PATH.as_posix(),
        "launcher": LAUNCHER_NAME,
        "startup_method": "listener_mode_remote_display",
        "marker_presentation": "shaded_3mm_cad_spheres",
        "absolute_paths": False,
        "previews": preview_relatives,
    }
    (package_dir / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    result = {"package_dir": package_dir, "database": database_destination}
    if archive:
        archive_path = Path(shutil.make_archive(str(output_dir / PACKAGE_NAME), "zip", output_dir, PACKAGE_NAME))
        result["archive"] = archive_path
    return result
