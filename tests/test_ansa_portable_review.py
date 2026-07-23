from __future__ import annotations

import json
import zipfile

from weld_core.ansa_portable_review import (
    DATABASE_RELATIVE_PATH,
    DISPLAY_SCRIPT_RELATIVE_PATH,
    LAUNCHER_NAME,
    MANIFEST_NAME,
    PACKAGE_NAME,
    REMOTE_LAUNCHER_NAME,
    build_portable_review,
)


def test_portable_review_is_relative_and_archived(tmp_path):
    source = tmp_path / "source.ansa"
    source.write_bytes(b"ANSA-test-database")
    preview = tmp_path / "detail.png"
    preview.write_bytes(b"PNG")
    output = tmp_path / "handoff"

    result = build_portable_review(source, output, preview_paths={"marker_detail": preview})
    package = result["package_dir"]
    manifest = json.loads((package / MANIFEST_NAME).read_text(encoding="utf-8"))
    display = (package / DISPLAY_SCRIPT_RELATIVE_PATH).read_text(encoding="utf-8")
    launcher = (package / LAUNCHER_NAME).read_text(encoding="utf-8")

    assert (package / DATABASE_RELATIVE_PATH).read_bytes() == b"ANSA-test-database"
    assert manifest["absolute_paths"] is False
    assert manifest["database"] == DATABASE_RELATIVE_PATH.as_posix()
    assert manifest["startup_method"] == "file_association_manual_display_script"
    assert manifest["previews"] == {"marker_detail": "previews/detail.png"}
    assert "base.SetViewButton" in display
    assert "guitk.BCTimerSingleShot(3000" in display
    assert "guitk.BCTimerSingleShot(10000" in display
    assert "COMPONENT_WELD_CAPTURE_STARTUP_DISPLAY" in display
    assert '"WIRE": "off"' in display
    assert '"Hot Points": "off"' in display
    assert "%~dp0" in launcher
    assert 'start "" "ansa\\component_weld_cad_review.ansa"' in launcher
    with zipfile.ZipFile(result["archive"]) as archive:
        assert f"{PACKAGE_NAME}/{DATABASE_RELATIVE_PATH.as_posix()}" in archive.namelist()
        assert f"{PACKAGE_NAME}/{DISPLAY_SCRIPT_RELATIVE_PATH.as_posix()}" in archive.namelist()
        assert f"{PACKAGE_NAME}/{REMOTE_LAUNCHER_NAME}" not in archive.namelist()
        assert f"{PACKAGE_NAME}/previews/detail.png" in archive.namelist()
