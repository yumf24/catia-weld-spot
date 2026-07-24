"""Build an evaluation-only weld operating frontier for one completed run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.data_layout import register_managed_artifact, sha256_file  # noqa: E402
from weld_core.operating_frontier import (  # noqa: E402
    OperatingFrontierError,
    build_operating_frontier,
    historical_operating_frontier,
    operating_frontier_markdown,
)
from weld_core.schema import load_candidates, load_ground_truth  # noqa: E402


def _run_dir(value: str) -> Path:
    path = Path(value)
    if not path.is_dir():
        raise argparse.ArgumentTypeError("run directory must exist")
    return path


def _latest_run() -> Path:
    parent = REPO_ROOT / "data" / "component-weld-evaluation"
    runs = sorted(path for path in parent.iterdir() if path.is_dir())
    if not runs:
        raise OperatingFrontierError("no component-weld-evaluation run exists")
    return runs[-1]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-dir", type=_run_dir)
    group.add_argument("--latest-run", action="store_true")
    parser.add_argument("--historical-only", action="store_true", help="publish only the frozen RW01 observations")
    parser.add_argument("--ordering-name", default="candidate_document_order")
    args = parser.parse_args(argv)
    run_dir = (_latest_run() if args.latest_run else args.run_dir).resolve()
    try:
        if args.historical_only:
            frontier = historical_operating_frontier(str(run_dir.relative_to(REPO_ROOT)))
        else:
            frontier = build_operating_frontier(
                load_ground_truth(run_dir / "ground_truth.json"),
                load_candidates(run_dir / "candidates.json"),
                json.loads((run_dir / "planar_truth_adjudication.json").read_text(encoding="utf-8")),
                ordering_name=args.ordering_name,
            )
        json_path = run_dir / "operating_frontier.json"
        markdown_path = run_dir / "operating_frontier.md"
        json_path.write_text(json.dumps(frontier, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        markdown_path.write_text(operating_frontier_markdown(frontier), encoding="utf-8")
        register_managed_artifact(json_path, "operating_frontier", kind="json", sha256=sha256_file(json_path))
        register_managed_artifact(markdown_path, "operating_frontier_markdown", kind="markdown", sha256=sha256_file(markdown_path))
    except (OSError, ValueError, OperatingFrontierError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] evaluation-only operating frontier -> {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
