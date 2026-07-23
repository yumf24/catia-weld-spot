from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from weld_core.data_layout import find_run
from weld_core.data_layout import register_managed_artifact
from weld_core.general_plane_selection_error_analysis import (
    ErrorAnalysisInputError,
    build_error_analysis_report,
    build_expanded_gap_false_positive_attribution,
    load_and_join_error_analysis,
    render_error_analysis_markdown,
)


def _repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else Path.cwd() / path


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    run_dir = _repo_path(args.run_dir) if args.run_dir else (find_run(args.part_id) if args.part_id else None)
    names = {
        "evaluation": "general_plane_selection_evaluation.json",
        "pair_audit": "pair_audit.json",
        "selection_audit": "selection_audit.json",
    }
    values = {name: _repo_path(getattr(args, name)) if getattr(args, name) else None for name in names}
    if run_dir is not None:
        values = {name: value or run_dir / filename for name, value in values.items() for filename in [names[name]]}
    if any(value is None for value in values.values()):
        raise ErrorAnalysisInputError("provide --run-dir (or part_id) or all three explicit audit paths")
    return values["evaluation"], values["pair_audit"], values["selection_audit"]


def _write_report(report: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "general_plane_selection_error_analysis.json"
    markdown_path = output_dir / "general_plane_selection_error_analysis.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_error_analysis_markdown(report), encoding="utf-8")
    register_managed_artifact(json_path, "general_plane_selection_error_analysis", kind="json")
    register_managed_artifact(markdown_path, "general_plane_selection_error_analysis_markdown", kind="markdown")
    return json_path, markdown_path


def _load_join_from_run_dir(run_dir: Path):
    return load_and_join_error_analysis(
        run_dir / "general_plane_selection_evaluation.json",
        run_dir / "pair_audit.json",
        run_dir / "selection_audit.json",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate an offline generic plane-selection error-analysis report.")
    parser.add_argument("part_id", nargs="?")
    parser.add_argument("--run-dir")
    parser.add_argument("--evaluation")
    parser.add_argument("--pair-audit")
    parser.add_argument("--selection-audit")
    parser.add_argument("--baseline-run-dir", help="0.2 mm offline baseline run used to attribute a 1.5 mm candidate's false positives")
    parser.add_argument("--output-dir")
    args = parser.parse_args(argv)
    try:
        evaluation_path, pair_audit_path, selection_audit_path = _resolve_paths(args)
        joined = load_and_join_error_analysis(evaluation_path, pair_audit_path, selection_audit_path)
        pair_audit = json.loads(pair_audit_path.read_text(encoding="utf-8"))
        result = build_error_analysis_report(joined, pair_audit)
        if args.baseline_run_dir:
            baseline_joined = _load_join_from_run_dir(_repo_path(args.baseline_run_dir))
            result["expanded_gap_false_positive_attribution"] = build_expanded_gap_false_positive_attribution(
                baseline_joined, joined
            )
        output_dir = _repo_path(args.output_dir) if args.output_dir else evaluation_path.parent
        json_path, markdown_path = _write_report(result, output_dir)
    except (ErrorAnalysisInputError, OSError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] wrote {json_path}")
    print(f"[OK] wrote {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
