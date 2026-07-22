"""Show a managed pipeline run and the raw inputs it was derived from.

Usage:
    python scripts/inspect_run.py <part-id> [run-id]

Without ``run-id`` the newest run is shown. This command only reads manifests
and files; it never modifies CAD data or run state.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.data_layout import DataLayoutError, find_run, load_raw_manifest  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part_id")
    parser.add_argument("run_id", nargs="?")
    args = parser.parse_args(argv)
    try:
        run_dir = find_run(args.part_id, args.run_id)
        run = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        raw = load_raw_manifest(args.part_id)
    except DataLayoutError as exc:
        parser.error(str(exc))

    print(f"part-id: {args.part_id}")
    print(f"run-id: {run['run_id']}")
    print(f"status: {run.get('status', 'unknown')}")
    print(f"run directory: {run_dir.relative_to(REPO_ROOT)}")
    print(f"raw manifest: {run.get('raw_manifest')}")
    print("raw inputs:")
    for role, info in raw["inputs"].items():
        print(f"  {role}: {info['path']}  sha256={info.get('sha256', '')}")
    print("artifacts:")
    for name, info in run.get("artifacts", {}).items():
        print(f"  {name}: {info['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
