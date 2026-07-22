from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.data_layout import DATA_ROOT, find_run, register_managed_artifact
from weld_core.general_plane_selection_error_analysis import build_optimization_recommendation_backlog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an offline evidence-backed plane-selection optimization backlog.")
    parser.add_argument("part_id")
    parser.add_argument("--run-dir")
    parser.add_argument("--output-dir")
    args = parser.parse_args(argv)
    try:
        run_dir = Path(args.run_dir) if args.run_dir else find_run(args.part_id, root=DATA_ROOT)
        output_dir = Path(args.output_dir) if args.output_dir else run_dir
        error_report = json.loads((run_dir / "general_plane_selection_error_analysis.json").read_text(encoding="utf-8"))
        sweep_report = json.loads((run_dir / "general_plane_selection_parameter_sweep.json").read_text(encoding="utf-8"))
        backlog = build_optimization_recommendation_backlog(error_report, sweep_report)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "general_plane_selection_optimization_backlog.json"
        output_path.write_text(json.dumps(backlog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        register_managed_artifact(output_path, "general_plane_selection_optimization_backlog", kind="json")
    except (OSError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"wrote {len(backlog['recommendations'])} offline optimization recommendations -> {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
