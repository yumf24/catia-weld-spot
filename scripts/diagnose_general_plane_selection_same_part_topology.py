from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.controlled_same_part_policy import diagnose_same_part_topology, render_same_part_topology_markdown
from weld_core.data_layout import DATA_ROOT, RAW_DATA_ROOT, find_run, load_raw_manifest, register_managed_artifact
from weld_core.general_plane_selection import general_faces_from_step_groups
from weld_core.step_geometry import parse_step_faces


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline exact same-part topology and geometry diagnosis.")
    parser.add_argument("part_id")
    parser.add_argument("--run-dir", help="Managed run directory containing offline evaluation and selection audits.")
    parser.add_argument("--output-dir", help="Override output directory (defaults to --run-dir).")
    args = parser.parse_args(argv)
    try:
        run_dir = Path(args.run_dir) if args.run_dir else find_run(args.part_id, root=DATA_ROOT)
        output_dir = Path(args.output_dir) if args.output_dir else run_dir
        evaluation = json.loads((run_dir / "general_plane_selection_evaluation.json").read_text(encoding="utf-8"))
        selection = json.loads((run_dir / "selection_audit.json").read_text(encoding="utf-8"))
        raw_manifest = load_raw_manifest(args.part_id, RAW_DATA_ROOT)
        primary_path = RAW_DATA_ROOT / args.part_id / raw_manifest["inputs"]["primary_model"]["path"]
        report = diagnose_same_part_topology(
            general_faces_from_step_groups(parse_step_faces(str(primary_path))),
            baseline_true_positives=evaluation["summary"]["true_positives"],
            offline_truth_face_ids=(row["face_id"] for row in evaluation["true_positive_faces"] + evaluation["false_negative_faces"]),
            baseline_predicted_face_ids=(row["face_id"] for row in selection["selected_faces"]),
        )
        report.update({"part_id": args.part_id, "run_id": selection.get("run_id"), "source": {"role": "primary_model", "path": str(primary_path)}})
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "general_plane_selection_same_part_topology_diagnosis.json"
        markdown_path = output_dir / "general_plane_selection_same_part_topology_diagnosis.md"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        markdown_path.write_text(render_same_part_topology_markdown(report), encoding="utf-8")
        register_managed_artifact(json_path, "general_plane_selection_same_part_topology_diagnosis", kind="json")
        register_managed_artifact(markdown_path, "general_plane_selection_same_part_topology_diagnosis_markdown", kind="markdown")
    except (KeyError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"wrote {report['review_count']} offline same-part topology reviews -> {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
