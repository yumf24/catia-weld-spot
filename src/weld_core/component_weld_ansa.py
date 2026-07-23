"""Build the evaluation-only ANSA marker package for a component run."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ANSA_VERSION = "24.1.1"
LAYERS = {
    "TP_TRUTH": "green",
    "TP_CANDIDATE": "green",
    "FP_CANDIDATE": "red",
    "FN_TRUTH": "yellow",
    "MATCH_LINK": "neutral",
}


def build_ansa_layers(error_analysis: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Convert traceable point classifications into importable marker rows."""
    layers = {name: [] for name in LAYERS}
    for row in error_analysis["true_positives"]:
        layers["TP_TRUTH"].append({"source_id": row["ground_truth_id"], **_point(row["ground_truth_position_mm"])})
        layers["TP_CANDIDATE"].append({"source_id": row["candidate_id"], "faces": ";".join(row["candidate_faces"]), **_point(row["candidate_position_mm"])})
        layers["MATCH_LINK"].append({"source_id": f"{row['ground_truth_id']}->{row['candidate_id']}", **_link(row["ground_truth_position_mm"], row["candidate_position_mm"])})
    for row in error_analysis["false_positives"]:
        layers["FP_CANDIDATE"].append({"source_id": row["candidate_id"], "faces": ";".join(row["candidate_faces"]), **_point(row["candidate_position_mm"])})
    for row in error_analysis["false_negatives"]:
        layers["FN_TRUTH"].append({"source_id": row["ground_truth_id"], **_point(row["ground_truth_position_mm"])})
    expected = {"TP_TRUTH": len(error_analysis["true_positives"]), "TP_CANDIDATE": len(error_analysis["true_positives"]), "FP_CANDIDATE": len(error_analysis["false_positives"]), "FN_TRUTH": len(error_analysis["false_negatives"]), "MATCH_LINK": len(error_analysis["true_positives"])}
    if {name: len(rows) for name, rows in layers.items()} != expected:
        raise ValueError("ANSA marker rows do not match point-level error analysis")
    return layers


def _point(position: list[float]) -> dict[str, float]:
    return {"x_mm": position[0], "y_mm": position[1], "z_mm": position[2]}


def _link(start: list[float], end: list[float]) -> dict[str, float]:
    return {"x1_mm": start[0], "y1_mm": start[1], "z1_mm": start[2], "x2_mm": end[0], "y2_mm": end[1], "z2_mm": end[2]}


def write_ansa_package(run_dir: Path) -> dict[str, Any]:
    """Write CSV layers, manifest and self-contained ANSA import script."""
    analysis_path = run_dir / "weld_point_error_analysis.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    layers = build_ansa_layers(analysis)
    ansa_dir = run_dir / "ansa"
    ansa_dir.mkdir(exist_ok=True)
    layer_files: dict[str, dict[str, Any]] = {}
    for name, rows in layers.items():
        path = ansa_dir / f"{name}.csv"
        fields = list(rows[0]) if rows else (["source_id", "x1_mm", "y1_mm", "z1_mm", "x2_mm", "y2_mm", "z2_mm"] if name == "MATCH_LINK" else ["source_id", "x_mm", "y_mm", "z_mm"])
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        layer_files[name] = {"path": str(path.relative_to(run_dir)).replace("\\", "/"), "color": LAYERS[name], "count": len(rows), "source": "weld_point_error_analysis.json"}
    script_path = ansa_dir / "ansa_import.py"
    script_path.write_text(_ansa_import_script(), encoding="utf-8")
    manifest = {"format_version": 1, "required_ansa_version": ANSA_VERSION, "marker_semantics": "visual_markers_not_fe_spotwelds", "source_error_analysis": "weld_point_error_analysis.json", "layers": layer_files, "import_script": "ansa/ansa_import.py"}
    (run_dir / "ansa_import_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _ansa_import_script() -> str:
    return '''"""ANSA v24.1.1 visual-marker importer; never creates SPOTWELD connectors."""
import csv
import os
from ansa import base, constants

ROOT = os.path.dirname(os.path.abspath(__file__))
COLORS = {"TP_TRUTH": "GREEN", "TP_CANDIDATE": "GREEN", "FP_CANDIDATE": "RED", "FN_TRUTH": "YELLOW", "MATCH_LINK": "GRAY"}

def marker_set(name):
    marker = base.CreateEntity(constants.NASTRAN, "SET", {"Name": name})
    # ANSA v24.1.1 does not expose ``base.SetEntityColor``.  The layer colour
    # remains explicit in the import manifest/CSV package; the Set name is the
    # stable ANSA-visible layer identifier used for display filtering.
    return marker

def add_nodes(name, rows):
    group = marker_set(name)
    for row in rows:
        node = base.CreateEntity(constants.NASTRAN, "GRID", {"X1": float(row["x_mm"]), "X2": float(row["y_mm"]), "X3": float(row["z_mm"]), "Name": row["source_id"]})
        base.AddToSet(group, [node])

def main():
    # GRID nodes are display markers only. MATCH_LINK is represented as a Set
    # of paired endpoint nodes; no FE connectors, elements or SPOTWELDs exist.
    for name in ("TP_TRUTH", "TP_CANDIDATE", "FP_CANDIDATE", "FN_TRUTH"):
        with open(os.path.join(ROOT, name + ".csv"), newline="") as handle:
            add_nodes(name, list(csv.DictReader(handle)))
    links = marker_set("MATCH_LINK")
    with open(os.path.join(ROOT, "MATCH_LINK.csv"), newline="") as handle:
        for row in csv.DictReader(handle):
            for suffix in ("1", "2"):
                node = base.CreateEntity(constants.NASTRAN, "GRID", {"X1": float(row["x" + suffix + "_mm"]), "X2": float(row["y" + suffix + "_mm"]), "X3": float(row["z" + suffix + "_mm"]), "Name": row["source_id"] + ":" + suffix})
                base.AddToSet(links, [node])

if __name__ == "__main__":
    main()
'''
