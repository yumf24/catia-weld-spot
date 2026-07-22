from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from weld_core.data_layout import find_run
from weld_core.general_plane_selection_error_analysis import ErrorAnalysisInputError, load_and_join_error_analysis


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Join offline generic plane-selection evaluation and audit artifacts.")
    parser.add_argument("part_id", nargs="?")
    parser.add_argument("--run-dir")
    parser.add_argument("--evaluation")
    parser.add_argument("--pair-audit")
    parser.add_argument("--selection-audit")
    args = parser.parse_args(argv)
    try:
        result = load_and_join_error_analysis(*_resolve_paths(args))
    except (ErrorAnalysisInputError, OSError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
