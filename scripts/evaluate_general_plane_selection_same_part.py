from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.data_layout import DATA_ROOT, find_run, register_managed_artifact
from weld_core.general_plane_selection_error_analysis import build_same_part_risk_report, render_same_part_risk_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write an offline same-part plane-selection risk report from a parameter sweep.")
    parser.add_argument("part_id")
    parser.add_argument("--run-dir", help="Managed run directory containing general_plane_selection_parameter_sweep.json.")
    parser.add_argument("--output-dir", help="Override output directory (defaults to --run-dir).")
    args = parser.parse_args(argv)
    try:
        run_dir = Path(args.run_dir) if args.run_dir else find_run(args.part_id, root=DATA_ROOT)
        output_dir = Path(args.output_dir) if args.output_dir else run_dir
        sweep = json.loads((run_dir / "general_plane_selection_parameter_sweep.json").read_text(encoding="utf-8"))
        report = build_same_part_risk_report(sweep)
        report.update({"part_id": args.part_id, "run_id": json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["run_id"]})
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "general_plane_selection_same_part_evaluation.json"
        markdown_path = output_dir / "general_plane_selection_same_part_evaluation.md"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        markdown_path.write_text(render_same_part_risk_markdown(report), encoding="utf-8")
        register_managed_artifact(json_path, "general_plane_selection_same_part_evaluation", kind="json")
        register_managed_artifact(markdown_path, "general_plane_selection_same_part_evaluation_markdown", kind="markdown")
    except (KeyError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"wrote offline same-part risk report -> {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
