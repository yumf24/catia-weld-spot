from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.controlled_same_part_policy import (  # noqa: E402
    evaluate_controlled_pair_policy_replay,
    replay_controlled_pair_policies,
)
from weld_core.data_layout import DATA_ROOT, find_run, register_managed_artifact  # noqa: E402


def _permissive_audit_from_registered_primary_audits(run_dir: Path) -> dict:
    """Compose one replay audit from exact primary-model audits already measured once."""

    pair_audit = json.loads((run_dir / "pair_audit.json").read_text(encoding="utf-8"))
    topology = json.loads((run_dir / "general_plane_selection_same_part_topology_diagnosis.json").read_text(encoding="utf-8"))
    rows = []
    structural_reasons = {"zero_area_intersection", "projected_aabb_no_overlap"}
    for row in pair_audit["pairs"]:
        if row["part_a"] == row["part_b"] or row["normal_angle_deg"] is None or row["plane_gap_mm"] is None:
            continue
        if row["normal_angle_deg"] > 0.5 or row["plane_gap_mm"] > 1.5:
            continue
        reason = row["reason"]
        exact_reason = reason if reason in structural_reasons or str(reason).startswith("projection_failed:") else None
        area, coverage_a, coverage_b = row["common_area_mm2"], row["coverage_a"], row["coverage_b"]
        rows.append({
            "pair_id": row["id"], "face_a_id": row["face_a_id"], "face_b_id": row["face_b_id"],
            "same_part_relation": "different_parts", "topology_class": "not_same_part",
            "normal_angle_deg": row["normal_angle_deg"], "gap_mm": row["plane_gap_mm"],
            "exact_common_area_mm2": area, "exact_coverage_a": coverage_a, "exact_coverage_b": coverage_b,
            "effective_width_mm": min(row["aabb_overlap_width_mm"] or 0.0, row["aabb_overlap_height_mm"] or 0.0),
            "score": area * min(coverage_a, coverage_b), "exact_reason": exact_reason,
        })
    rows.extend(topology["pairs"])
    rows.sort(key=lambda row: row["pair_id"])
    return {
        "format_version": 1, "scope": "offline_controlled_pair_geometry_audit",
        "production_behavior_changed": False,
        "source": "registered_primary_model_exact_audits", "pair_count": len(rows), "pairs": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline controlled same-part policy search.")
    parser.add_argument("part_id")
    parser.add_argument("--run-dir")
    args = parser.parse_args(argv)
    try:
        run_dir = Path(args.run_dir) if args.run_dir else find_run(args.part_id, root=DATA_ROOT)
        evaluation = json.loads((run_dir / "general_plane_selection_evaluation.json").read_text(encoding="utf-8"))
        audit = _permissive_audit_from_registered_primary_audits(run_dir)
        replay = replay_controlled_pair_policies(audit)
        truth = [row["face_id"] for row in evaluation["true_positive_faces"] + evaluation["false_negative_faces"]]
        report = evaluate_controlled_pair_policy_replay(replay, truth)
        report.update({"part_id": args.part_id, "run_id": evaluation.get("run_id"), "geometry_audit": audit})
        path = run_dir / "general_plane_selection_controlled_pair_policy_search.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        register_managed_artifact(path, "general_plane_selection_controlled_pair_policy_search", kind="json")
    except (KeyError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"wrote {report['case_count']} offline controlled policy cases -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
