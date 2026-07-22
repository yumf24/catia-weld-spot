from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from weld_core.data_layout import RAW_DATA_ROOT, find_run, load_raw_manifest, register_managed_artifact
from weld_core.general_plane_selection import general_faces_from_step_groups
from weld_core.general_plane_selection_evaluation import evaluate_general_plane_selection, evaluation_markdown
from weld_core.schema import load_faces
from weld_core.step_geometry import parse_step_faces


def _repo_path(path: str | Path) -> Path:
    value = Path(path)
    if value.is_absolute():
        return value
    return Path.cwd() / value


def _manifest_input_path(part_id: str, role: str) -> Path:
    manifest = load_raw_manifest(part_id)
    info = manifest["inputs"].get(role)
    if not isinstance(info, dict) or not isinstance(info.get("path"), str):
        raise SystemExit(f"raw manifest for {part_id!r} has no {role!r} input")
    return RAW_DATA_ROOT / part_id / info["path"]


def _selected_ids(path: Path) -> list[str]:
    doc = load_faces(path)
    return [face.id for face in doc.faces if face.surface_type == "planar"]


def _resolve_inputs(args: argparse.Namespace) -> tuple[Path, Path, Path, Path, Path]:
    run_dir = _repo_path(args.run_dir) if args.run_dir else None
    if args.part_id and run_dir is None:
        run_dir = find_run(args.part_id)
    if args.part_id:
        source_step = _repo_path(args.source_step) if args.source_step else _manifest_input_path(args.part_id, "primary_model")
        reference_step = (
            _repo_path(args.reference_step)
            if args.reference_step
            else _manifest_input_path(args.part_id, "surface_reference")
        )
    else:
        if not args.source_step or not args.reference_step:
            raise SystemExit("either part_id or both --source-step and --reference-step are required")
        source_step = _repo_path(args.source_step)
        reference_step = _repo_path(args.reference_step)
    if args.selected_faces:
        selected_faces = _repo_path(args.selected_faces)
    elif run_dir is not None:
        selected_faces = run_dir / "faces.general-selected.json"
    else:
        raise SystemExit("--selected-faces is required when no --run-dir is provided")
    output_json = _repo_path(args.output_json) if args.output_json else (run_dir / "general_plane_selection_evaluation.json" if run_dir else Path("general_plane_selection_evaluation.json"))
    output_md = _repo_path(args.output_markdown) if args.output_markdown else output_json.with_suffix(".md")
    return source_step, reference_step, selected_faces, output_json, output_md


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate generic planar face selection with explicit offline CAD references.")
    parser.add_argument("part_id", nargs="?")
    parser.add_argument("--run-dir")
    parser.add_argument("--source-step")
    parser.add_argument("--reference-step")
    parser.add_argument("--selected-faces")
    parser.add_argument("--output-json")
    parser.add_argument("--output-markdown")
    args = parser.parse_args(argv)

    source_step, reference_step, selected_faces, output_json, output_md = _resolve_inputs(args)
    source_faces = general_faces_from_step_groups(parse_step_faces(str(source_step)))
    reference_faces = general_faces_from_step_groups(parse_step_faces(str(reference_step)))
    result = evaluate_general_plane_selection(source_faces, reference_faces, _selected_ids(selected_faces))
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    output_md.write_text(evaluation_markdown(result), encoding="utf-8")
    register_managed_artifact(output_json, "general_plane_selection_evaluation", kind="json")
    register_managed_artifact(output_md, "general_plane_selection_evaluation_markdown", kind="markdown")
    summary = result["summary"]
    print(
        "TP/FP/FN="
        f"{summary['true_positives']}/{summary['false_positives']}/{summary['false_negatives']} "
        f"precision={summary['precision']:.3f} recall={summary['recall']:.3f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
