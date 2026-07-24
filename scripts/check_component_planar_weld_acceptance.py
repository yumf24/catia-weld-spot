"""Check the frozen PW06 component planar-weld acceptance gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _latest_run() -> Path:
    parent = REPO_ROOT / "data" / "component-weld-evaluation"
    runs = sorted(path for path in parent.iterdir() if path.is_dir() and (path / "manifest.json").is_file())
    if not runs:
        raise ValueError("no component-weld-evaluation run exists")
    return runs[-1]


def check_acceptance(run_dir: Path) -> tuple[bool, dict]:
    report = json.loads((run_dir / "weld_point_evaluation.json").read_text(encoding="utf-8"))
    full = report["summary"]
    planar = report.get("planar_supported_summary", {})
    checks = {
        "full_ground_truth_reported": full.get("ground_truth_count") == 286,
        "planar_supported_reported": planar.get("ground_truth_count", 0) > 0,
        "planar_supported_recall_at_least_0_80": planar.get("recall", 0.0) >= 0.80,
        "candidate_count_500_to_1000": 500 <= full.get("candidate_count", 0) <= 1000,
    }
    return all(checks.values()), {"run_dir": str(run_dir), "checks": checks, "full_summary": full, "planar_supported_summary": planar}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--latest-run", action="store_true", help="check the most recent managed component run")
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args(argv)
    if bool(args.latest_run) == bool(args.run_dir):
        parser.error("provide exactly one of --latest-run or --run-dir")
    try:
        passed, result = check_acceptance(_latest_run() if args.latest_run else args.run_dir.resolve())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
