"""Build ANSA-v24.1.1 visual marker files for an evaluated component run."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.component_weld_ansa import write_ansa_package  # noqa: E402
from weld_core.data_layout import register_artifact, sha256_file  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args(argv)
    run_dir = args.run_dir.resolve()
    try:
        manifest = write_ansa_package(run_dir)
        for name, item in manifest["layers"].items():
            path = run_dir / item["path"]
            register_artifact(run_dir, f"ansa_{name.lower()}", path, kind="csv", sha256=sha256_file(path), count=item["count"])
        for name, path, kind in (("ansa_import_manifest", run_dir / "ansa_import_manifest.json", "json"), ("ansa_import_script", run_dir / "ansa" / "ansa_import.py", "python")):
            register_artifact(run_dir, name, path, kind=kind, sha256=sha256_file(path))
    except (OSError, ValueError, KeyError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] ANSA visual marker package -> {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
