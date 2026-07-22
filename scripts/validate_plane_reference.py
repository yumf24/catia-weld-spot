"""Validate a registered model's planar faces against its STEP surface reference.

By default this parses the registered ``primary_model`` STEP input. Pass
``--faces`` after a CATIA run to validate its ``faces.enriched.json`` using the
same reference. Results are always written to a managed run directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.data_layout import (  # noqa: E402
    DataLayoutError,
    create_run,
    load_raw_manifest,
    register_artifact,
    update_run_manifest,
    verify_raw_inputs,
)
from weld_core.plane_validation import (  # noqa: E402
    document_plane_faces,
    step_plane_faces,
    validate_plane_faces,
)
from weld_core.schema import load_faces  # noqa: E402
from weld_core.step_geometry import parse_step_faces  # noqa: E402


def _input_path(manifest: dict, part_id: str, role: str) -> Path:
    try:
        relative = manifest["inputs"][role]["path"]
    except KeyError as exc:
        raise DataLayoutError(f"raw manifest for {part_id!r} has no {role!r} input") from exc
    return REPO_ROOT / "raw_data" / part_id / relative


def _markdown_report(result: dict, part_id: str, source: str, reference: str) -> str:
    summary = result["summary"]
    return "\n".join(
        [
            f"# {part_id} 平面验证报告",
            "",
            f"- 算法来源：`{source}`",
            f"- 真实平面参考：`{reference}`",
            f"- 结论：**{'通过' if summary['passed'] else '未通过'}**",
            "",
            "## 汇总",
            "",
            "| 指标 | 数值 |",
            "| --- | ---: |",
            f"| 算法平面面数 | {summary['algorithm_planar_faces']} |",
            f"| 参考平面面数 | {summary['reference_planar_faces']} |",
            f"| 匹配算法面（TP） | {summary['true_positives']} |",
            f"| 误检算法面（FP） | {summary['false_positives']} |",
            f"| 漏检参考面（FN） | {summary['false_negatives']} |",
            f"| Precision | {summary['precision']:.2%} |",
            f"| Recall | {summary['recall']:.2%} |",
            "",
            "匹配条件：同零件、法向夹角 ≤ 0.1°、平面距离 ≤ 0.02 mm，且投影 AABB 存在正面积重叠。"
            "面切分允许多对多匹配；逐面明细见 `plane_validation.json`。",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part_id", help="registered raw-data id, e.g. component-simplify")
    parser.add_argument("--faces", type=Path, help="CATIA/STEP-enriched faces.json to validate")
    parser.add_argument("--run-dir", type=Path, help="existing managed run directory for output")
    parser.add_argument("--run-label", default="plane-validation", help="label for a new managed run")
    args = parser.parse_args()
    if args.run_dir and not args.run_dir.is_dir():
        parser.error(f"--run-dir does not exist: {args.run_dir}")
    if args.run_dir and args.run_label != "plane-validation":
        parser.error("--run-label cannot be used with --run-dir")

    run_dir: Path | None = None
    created_run = False
    try:
        raw_inputs = verify_raw_inputs(args.part_id)
        raw_manifest = load_raw_manifest(args.part_id)
        model_path = _input_path(raw_manifest, args.part_id, "primary_model")
        reference_path = _input_path(raw_manifest, args.part_id, "surface_reference")
        created_run = args.run_dir is None
        if created_run:
            run_dir, _ = create_run(
                args.part_id,
                args.run_label,
                parameters={"validation": "plane-reference", "source_faces": str(args.faces) if args.faces else None},
            )
        else:
            run_dir = args.run_dir.resolve()
            run_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            if run_manifest.get("part_id") != args.part_id:
                raise DataLayoutError(f"run {run_dir} belongs to {run_manifest.get('part_id')!r}, not {args.part_id!r}")

        reference_faces = step_plane_faces(parse_step_faces(str(reference_path)))
        if args.faces:
            source_faces = document_plane_faces(load_faces(args.faces))
            source_label = str(args.faces)
            source_kind = "faces_json"
        else:
            source_faces = step_plane_faces(parse_step_faces(str(model_path)))
            source_label = str(model_path.relative_to(REPO_ROOT))
            source_kind = "step"
        result = validate_plane_faces(source_faces, reference_faces)
        result.update(
            {
                "part_id": args.part_id,
                "source": {"kind": source_kind, "path": source_label},
                "reference": str(reference_path.relative_to(REPO_ROOT)),
                "raw_inputs": raw_inputs,
                "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
        )
        json_path = run_dir / "plane_validation.json"
        report_path = run_dir / "plane_validation.md"
        json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        report_path.write_text(_markdown_report(result, args.part_id, source_label, result["reference"]), encoding="utf-8")
        register_artifact(run_dir, "plane_validation", json_path, source_kind=source_kind)
        register_artifact(run_dir, "plane_validation_report", report_path, kind="markdown")
        if created_run:
            update_run_manifest(run_dir, status="completed", completed_at=datetime.now().astimezone().isoformat(timespec="seconds"))
        summary = result["summary"]
        print(f"[{'PASS' if summary['passed'] else 'FAIL'}] precision={summary['precision']:.2%}, recall={summary['recall']:.2%}; {json_path}")
        return 0 if summary["passed"] else 1
    except Exception as exc:
        if run_dir is not None and created_run:
            update_run_manifest(run_dir, status="failed", error=str(exc), failed_at=datetime.now().astimezone().isoformat(timespec="seconds"))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
