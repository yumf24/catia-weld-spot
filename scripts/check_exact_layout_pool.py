"""Validate that every exact interface region has a certified full layout pool."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.component_weld_evaluation import COMPONENT_EVALUATION_RUN_ROOT  # noqa: E402


def _latest_run() -> Path:
    runs = sorted(path for path in COMPONENT_EVALUATION_RUN_ROOT.iterdir() if (path / "manifest.json").is_file())
    if not runs:
        raise ValueError("no component weld evaluation runs found")
    return runs[-1]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest-run", action="store_true")
    group.add_argument("--run-dir", type=Path)
    args = parser.parse_args(argv)
    run_dir = _latest_run() if args.latest_run else args.run_dir
    assert run_dir is not None
    regions = json.loads((run_dir / "interface_region_audit.json").read_text(encoding="utf-8")).get("regions", [])
    audit = json.loads((run_dir / "coverage_layout_audit.json").read_text(encoding="utf-8"))
    rows = {row.get("interface_id"): row for row in audit.get("interfaces", [])}
    failures = []
    for region in regions:
        row = rows.get(region["id"])
        if not row or row.get("layout_status") != "certified" or row.get("retained_count", 0) < 1:
            failures.append(region["id"])
            continue
        if row.get("max_certificate_distance_mm", float("inf")) > 10.0 + 1e-9:
            failures.append(region["id"])
    if failures:
        print(f"[FAIL] uncertified or empty exact layouts: {', '.join(failures[:10])}", file=sys.stderr)
        return 1
    print(f"[OK] {len(regions)} exact regions have certified nonempty full layout pools")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
