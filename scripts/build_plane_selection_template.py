"""Build auditable labels from registered STEP inputs (use --dry-run for S03)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.data_layout import load_raw_manifest, verify_raw_inputs  # noqa: E402
from weld_core.plane_reference_labels import (  # noqa: E402
    build_reference_face_labels,
    indexed_planar_faces,
)
from weld_core.step_geometry import parse_step_faces  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part_id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.dry_run and args.output:
        parser.error("--dry-run cannot be combined with --output")
    manifest = load_raw_manifest(args.part_id)
    raw_inputs = verify_raw_inputs(args.part_id)
    base = REPO_ROOT / "raw_data" / args.part_id
    source = base / manifest["inputs"]["primary_model"]["path"]
    reference = base / manifest["inputs"]["surface_reference"]["path"]
    result = build_reference_face_labels(
        indexed_planar_faces(parse_step_faces(str(source))),
        indexed_planar_faces(parse_step_faces(str(reference))),
    )
    result.update({"part_id": args.part_id, "raw_inputs": raw_inputs})
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = result["summary"]
    print(f"[{'PASS' if summary['passed'] else 'FAIL'}] labels={summary['selected_labels']}/{summary['reference_planar_faces']}")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
