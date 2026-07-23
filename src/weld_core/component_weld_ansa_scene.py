"""Pure-Python contract helpers for the CAD-backed ANSA weld review scene."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .data_layout import sha256_file


ANSA_VERSION = "24.1.1"
SCENE_DATABASE = "ansa/component_weld_cad_review.ansa"
SCENE_SCREENSHOTS = {
    "isometric": "ansa/views/component_weld_isometric.png",
    "front": "ansa/views/component_weld_front.png",
    "right": "ansa/views/component_weld_right.png",
    "top": "ansa/views/component_weld_top.png",
}
MARKER_RADIUS_MM = 3.0
SPHERE_FACE_COUNT = 6
LAYER_COLORS = {
    "TP_TRUTH": "GREEN",
    "TP_CANDIDATE": "GREEN",
    "FP_CANDIDATE": "RED",
    "FN_TRUTH": "YELLOW",
}
LAYER_RGB = {
    "TP_TRUTH": (0, 180, 0),
    "TP_CANDIDATE": (0, 180, 0),
    "FP_CANDIDATE": (220, 0, 0),
    "FN_TRUTH": (240, 200, 0),
}
LINK_LAYER = "MATCH_LINK"


def load_scene_inputs(run_dir: Path, repository_root: Path) -> dict[str, Any]:
    """Validate a completed component run and return its CAD/marker scene inputs."""
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("part_id") != "component" or manifest.get("status") != "completed":
        raise ValueError("scene generation requires a completed component evaluation run")
    raw_manifest_path = repository_root / "raw_data" / "component" / "manifest.json"
    raw_manifest = json.loads(raw_manifest_path.read_text(encoding="utf-8"))
    primary = raw_manifest.get("inputs", {}).get("primary_model", {})
    if primary.get("path") != "component.step":
        raise ValueError("component raw manifest must register component.step as primary_model")
    cad_path = raw_manifest_path.parent / primary["path"]
    if not cad_path.is_file() or sha256_file(cad_path) != primary.get("sha256"):
        raise ValueError("registered component.step is missing or its SHA-256 does not match")
    analysis_path = run_dir / "weld_point_error_analysis.json"
    if not analysis_path.is_file():
        raise ValueError("run has no weld_point_error_analysis.json")
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    required = ("true_positives", "false_positives", "false_negatives")
    if any(name not in analysis for name in required):
        raise ValueError("point error analysis is missing a required classification")
    return {
        "cad_path": cad_path,
        "analysis": analysis,
        "marker_counts": {
            "TP_TRUTH": len(analysis["true_positives"]),
            "TP_CANDIDATE": len(analysis["true_positives"]),
            "FP_CANDIDATE": len(analysis["false_positives"]),
            "FN_TRUTH": len(analysis["false_negatives"]),
            LINK_LAYER: len(analysis["true_positives"]),
        },
    }


def scene_paths(run_dir: Path) -> dict[str, Path]:
    """Return all managed scene output paths without writing them."""
    return {
        "database": run_dir / SCENE_DATABASE,
        "validation": run_dir / "ansa_cad_scene_validation.json",
        "report": run_dir / "ansa_cad_scene_validation.md",
        "log": run_dir / "ansa" / "component_weld_cad_review.log",
        **{f"screenshot_{name}": run_dir / path for name, path in SCENE_SCREENSHOTS.items()},
    }
