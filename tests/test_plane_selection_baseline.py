"""Local regression coverage for the read-only selection baseline command."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_MODEL = REPO_ROOT / "raw_data" / "component-simplify" / "component_simplify.step"


@pytest.mark.skipif(not RAW_MODEL.is_file(), reason="local component-simplify validation assets are gitignored")
def test_component_simplify_baseline_reports_verified_hashes_and_face_counts():
    result = subprocess.run(
        [sys.executable, "scripts/check_plane_selection_baseline.py", "component-simplify", "--json"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    report = json.loads(result.stdout)
    assert {record["role"] for record in report["raw_inputs"]} == {"primary_model", "surface_reference"}
    assert report["primary_model"] == {"faces": 2834, "planar_faces": 525}
    assert report["surface_reference"] == {"faces": 89, "planar_faces": 40}
