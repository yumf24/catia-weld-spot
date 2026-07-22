from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.data_layout import DATA_ROOT, RAW_DATA_ROOT, find_run, load_raw_manifest, register_managed_artifact
from weld_core.general_plane_selection import general_faces_from_step_groups
from weld_core.general_plane_selection_error_analysis import (
    render_controlled_parameter_sweep_markdown,
    run_controlled_parameter_sweep,
)
from weld_core.step_geometry import parse_step_faces


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the fixed offline generic-plane-selection parameter sweep.")
    parser.add_argument("part_id")
    parser.add_argument("--run-dir", help="Managed run directory that receives the analysis artifacts.")
    parser.add_argument("--output-dir", help="Override output directory (defaults to --run-dir).")
    args = parser.parse_args(argv)
    try:
        run_dir = Path(args.run_dir) if args.run_dir else find_run(args.part_id, root=DATA_ROOT)
        output_dir = Path(args.output_dir) if args.output_dir else run_dir
        manifest = load_raw_manifest(args.part_id, RAW_DATA_ROOT)
        inputs = manifest["inputs"]
        primary = RAW_DATA_ROOT / args.part_id / inputs["primary_model"]["path"]
        reference = RAW_DATA_ROOT / args.part_id / inputs["surface_reference"]["path"]
        report = run_controlled_parameter_sweep(
            general_faces_from_step_groups(parse_step_faces(str(primary))),
            general_faces_from_step_groups(parse_step_faces(str(reference))),
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "general_plane_selection_parameter_sweep.json"
        markdown_path = output_dir / "general_plane_selection_parameter_sweep.md"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        markdown_path.write_text(render_controlled_parameter_sweep_markdown(report), encoding="utf-8")
        register_managed_artifact(json_path, "general_plane_selection_parameter_sweep", kind="json")
        register_managed_artifact(markdown_path, "general_plane_selection_parameter_sweep_markdown", kind="markdown")
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"wrote {report['case_count']} offline parameter sweep cases -> {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
