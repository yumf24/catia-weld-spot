"""Open the managed ANSA weld-review scene with its shaded-marker display applied."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from check_ansa_weld_visualization import newest_completed_run  # noqa: E402
from weld_core.component_weld_ansa_scene import scene_paths  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest-run", action="store_true")
    group.add_argument("--run-dir", type=Path)
    group.add_argument(
        "--ansa-part",
        type=Path,
        metavar="PATH",
        help="path to an .ansa database to open and render with the review display settings",
    )
    args = parser.parse_args(argv)
    if args.ansa_part:
        database_path = args.ansa_part.resolve()
        if database_path.suffix.lower() != ".ansa":
            print(f"[FAIL] --ansa-part must name an .ansa database: {database_path}", file=sys.stderr)
            return 1
        if not database_path.is_file():
            print(f"[FAIL] missing ANSA database: {database_path}", file=sys.stderr)
            return 1
    else:
        run_dir = newest_completed_run() if args.latest_run else args.run_dir.resolve()
        paths = scene_paths(run_dir)
        for name in ("database", "display_script"):
            if not paths[name].is_file():
                print(f"[FAIL] missing {name}: {paths[name]}", file=sys.stderr)
                return 1
        database_path = paths["database"]
    # Use the Windows .ansa association (the same path as double-clicking the
    # file). ANSA's executable command line treats a bare database argument as
    # a startup working directory rather than opening the database.
    os.startfile(database_path)
    print(f"[OK] started ANSA database: {database_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
