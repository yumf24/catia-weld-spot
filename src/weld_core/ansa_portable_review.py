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
PREVIEWS_RELATIVE_DIR = Path("previews")
README_NAME = "README.txt"
MANIFEST_NAME = "portable_review_manifest.json"
LAUNCHER_NAME = "open_component_weld_review.bat"


def display_script_source() -> str:
    """Return a portable ANSA startup/display script with no absolute paths."""
    return '''"""Shaded, topology-free display for the component weld review."""
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


apply_review_display()
'''


def launcher_source() -> str:
    """Return a Windows launcher that preserves the package working directory."""
    return r'''@echo off
setlocal
pushd "%~dp0"
start "" "ansa\component_weld_cad_review.ansa"
popd
'''


def readme_source() -> str:
    return """Component weld ANSA review package

Open `open_component_weld_review.bat` on Windows. It uses the local .ansa file
association and leaves ANSA interactive. The package has no repository-specific
paths.

`ANSA_TRANSL.py` applies Part-colour shaded display and disables Wire, CONS and
Hot Points so the 3 mm CAD weld markers render as round green/red/yellow spheres.
ANSA searches this file in the launch working directory. If a local ANSA setup
does not load startup scripts from the package directory, open and run
`ansa/apply_component_weld_review_display.py` manually after the database opens.

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
