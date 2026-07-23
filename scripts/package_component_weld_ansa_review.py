"""Create a self-contained, shareable ZIP for the component ANSA weld review."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from check_ansa_weld_visualization import newest_completed_run  # noqa: E402
from weld_core.ansa_portable_review import build_portable_review  # noqa: E402
from weld_core.component_weld_ansa_scene import SCENE_SCREENSHOTS, scene_paths  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest-run", action="store_true")
    group.add_argument("--run-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True, help="parent directory for the portable folder and ZIP")
    parser.add_argument("--no-archive", action="store_true", help="create only the portable directory")
    args = parser.parse_args(argv)
    run_dir = newest_completed_run() if args.latest_run else args.run_dir.resolve()
    database = scene_paths(run_dir)["database"]
    try:
        previews = {name: run_dir / relative for name, relative in SCENE_SCREENSHOTS.items()}
        result = build_portable_review(database, args.output_dir, preview_paths=previews, archive=not args.no_archive)
    except (OSError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] portable ANSA review directory: {result['package_dir']}")
    if "archive" in result:
        print(f"[OK] portable ANSA review ZIP: {result['archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
