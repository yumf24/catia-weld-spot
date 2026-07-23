from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.data_layout import DATA_ROOT, RAW_DATA_ROOT, find_run, load_raw_manifest, register_managed_artifact
from weld_core.general_plane_selection import general_faces_from_step_groups
from weld_core.general_plane_selection_gap_recovery import diagnose_gap_recovery
from weld_core.step_geometry import parse_step_faces


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline exact-overlap replay of 1.5-6 mm cross-part gap rejections.")
    parser.add_argument("part_id")
    parser.add_argument("--run-dir", help="Managed run directory containing the pair, evaluation, and AABB audits.")
    parser.add_argument("--output-dir", help="Override output directory (defaults to --run-dir).")
    args = parser.parse_args(argv)
    try:
        run_dir = Path(args.run_dir) if args.run_dir else find_run(args.part_id, root=DATA_ROOT)
        output_dir = Path(args.output_dir) if args.output_dir else run_dir
        pair_audit = json.loads((run_dir / "pair_audit.json").read_text(encoding="utf-8"))
        evaluation = json.loads((run_dir / "general_plane_selection_evaluation.json").read_text(encoding="utf-8"))
        aabb = json.loads((run_dir / "general_plane_selection_aabb_diagnosis.json").read_text(encoding="utf-8"))
        raw_manifest = load_raw_manifest(args.part_id, RAW_DATA_ROOT)
        primary_path = RAW_DATA_ROOT / args.part_id / raw_manifest["inputs"]["primary_model"]["path"]
        report = diagnose_gap_recovery(
            pair_audit, general_faces_from_step_groups(parse_step_faces(str(primary_path))),
            baseline_true_positives=evaluation["summary"]["true_positives"],
            false_negative_face_ids=(row["face_id"] for row in evaluation["false_negative_faces"]),
            aabb_prefilter_false_rejection_count=aabb["review_status_counts"]["prefilter_false_rejection"],
        )
        report.update({"part_id": args.part_id, "run_id": pair_audit.get("run_id"), "source": {"role": "primary_model", "path": str(primary_path)}})
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "general_plane_selection_gap_recovery_diagnosis.json"
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        register_managed_artifact(output_path, "general_plane_selection_gap_recovery_diagnosis", kind="json")
    except (KeyError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"wrote {report['review_count']} offline gap reviews -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
