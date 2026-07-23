"""Open the managed ANSA weld-review scene with its shaded-marker display applied."""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from check_ansa_weld_visualization import newest_completed_run, resolve_ansa_shortcut  # noqa: E402
from weld_core.component_weld_ansa_scene import scene_paths  # noqa: E402


def _custom_startup_script_source(database_path: Path) -> str:
    """Return an ANSA startup script for a caller-supplied database."""
    return f'''"""Open a caller-supplied ANSA database with review display settings."""
from ansa import base

DATABASE_PATH = {str(database_path)!r}


def main():
    if base.Open(DATABASE_PATH) != 0:
        raise RuntimeError("could not open ANSA database: " + DATABASE_PATH)
    base.SetViewButton({{
        "VIEWMODE": "PART",
        "SHADOW": "on",
        "WIRE": "off",
        "CONS": "off",
        "BOUNDS": "off",
        "M.Pnt.": "off",
        "C.NODE": "off",
        "GRIDs": "off",
        "Hot Points": "off",
    }})
    base.SetViewAngles("F10")
    base.ZoomAll()
'''


def _write_custom_startup_script(database_path: Path) -> Path:
    """Write a unique temporary ANSA startup script that survives GUI launch."""
    path = Path(tempfile.gettempdir()) / f"open_ansa_part_{uuid.uuid4().hex}.py"
    path.write_text(_custom_startup_script_source(database_path), encoding="utf-8")
    return path


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
        startup_script = _write_custom_startup_script(database_path)
        cwd = database_path.parent
    else:
        run_dir = newest_completed_run() if args.latest_run else args.run_dir.resolve()
        paths = scene_paths(run_dir)
        for name in ("database", "display_script", "startup_script"):
            if not paths[name].is_file():
                print(f"[FAIL] missing {name}: {paths[name]}", file=sys.stderr)
                return 1
        database_path = paths["database"]
        startup_script = paths["startup_script"]
        cwd = run_dir
    executable = resolve_ansa_shortcut()
    command = [str(executable), "-exec", f"load_script:{startup_script}", "-exec", "main"]
    subprocess.Popen(command, cwd=cwd)
    print(f"[OK] started ANSA review scene: {database_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
