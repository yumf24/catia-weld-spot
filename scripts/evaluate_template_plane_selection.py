"""Evaluate a managed frozen-template selection against the reference STEP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.data_layout import (DataLayoutError, load_raw_manifest, register_artifact, verify_raw_inputs)  # noqa: E402
from weld_core.exact_plane_selection_evaluation import evaluate_plane_selection, evaluation_markdown  # noqa: E402
from weld_core.plane_reference_labels import indexed_planar_faces  # noqa: E402
from weld_core.schema import load_faces  # noqa: E402
from weld_core.step_geometry import parse_step_faces  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part_id")
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        run_dir = args.run_dir.resolve()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("part_id") != args.part_id:
            raise ValueError("run directory part_id does not match requested part-id")
        verify_raw_inputs(args.part_id, roles=("primary_model", "surface_reference"))
        raw = load_raw_manifest(args.part_id)
        raw_dir = REPO_ROOT / "raw_data" / args.part_id
        primary = raw_dir / raw["inputs"]["primary_model"]["path"]
        reference = raw_dir / raw["inputs"]["surface_reference"]["path"]
        selected_doc = load_faces(run_dir / "faces.selected.json")
        primary_faces = indexed_planar_faces(parse_step_faces(str(primary)))
        available = {face.id: face for face in primary_faces}
        selected = []
        for record in selected_doc.faces:
            if record.id not in available:
                raise ValueError(f"selected face is absent or no longer planar in primary STEP: {record.id}")
            selected.append(available[record.id])
        reference_faces = indexed_planar_faces(parse_step_faces(str(reference)))
        result = evaluate_plane_selection(selected, reference_faces)
        json_path = run_dir / "plane_selection_evaluation.json"
        markdown_path = run_dir / "plane_selection_evaluation.md"
        json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        markdown_path.write_text(evaluation_markdown(result), encoding="utf-8")
        register_artifact(run_dir, "plane_selection_evaluation", json_path, **result["summary"])
        register_artifact(run_dir, "plane_selection_evaluation_report", markdown_path, kind="markdown")
        print(f"precision={result['summary']['precision']:.2%} recall={result['summary']['recall']:.2%} -> {run_dir}")
        return 0 if result["summary"]["passed"] else 1
    except (DataLayoutError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
