"""Open the managed ANSA weld-review scene with its shaded-marker display applied."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from check_ansa_weld_visualization import newest_completed_run, resolve_ansa_shortcut  # noqa: E402
from weld_core.component_weld_ansa_scene import scene_paths  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest-run", action="store_true")
    group.add_argument("--run-dir", type=Path)
    args = parser.parse_args(argv)
    run_dir = newest_completed_run() if args.latest_run else args.run_dir.resolve()
    paths = scene_paths(run_dir)
    for name in ("database", "display_script", "startup_script"):
        if not paths[name].is_file():
            print(f"[FAIL] missing {name}: {paths[name]}", file=sys.stderr)
            return 1
    executable = resolve_ansa_shortcut()
    command = [str(executable), "-exec", f"load_script:{paths['startup_script']}", "-exec", "main"]
    subprocess.Popen(command, cwd=run_dir)
    print(f"[OK] started ANSA review scene: {paths['database']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
