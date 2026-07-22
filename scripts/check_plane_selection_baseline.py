"""Report the verified component-simplify CAD-face selection baseline.

This is a read-only preflight: it validates every registered raw input before
parsing the primary model and the one-time reference fixture.  It creates no
run directory and changes no algorithm output.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.data_layout import DataLayoutError, load_raw_manifest, verify_raw_inputs  # noqa: E402
from weld_core.step_geometry import parse_step_faces  # noqa: E402


def _input_path(manifest: dict, part_id: str, role: str) -> Path:
    try:
        relative = manifest["inputs"][role]["path"]
    except KeyError as exc:
        raise DataLayoutError(f"raw manifest for {part_id!r} has no {role!r} input") from exc
    return REPO_ROOT / "raw_data" / part_id / relative


def _face_counts(path: Path) -> dict[str, int]:
    faces = [face for part_faces in parse_step_faces(str(path)).values() for face in part_faces]
    return {"faces": len(faces), "planar_faces": sum(face.is_planar for face in faces)}


def collect_baseline(part_id: str) -> dict:
    """Return hash-verified raw inputs and deterministic STEP face counts."""
    raw_inputs = verify_raw_inputs(part_id)
    manifest = load_raw_manifest(part_id)
    primary = _input_path(manifest, part_id, "primary_model")
    reference = _input_path(manifest, part_id, "surface_reference")
    return {
        "part_id": part_id,
        "raw_inputs": raw_inputs,
        "primary_model": _face_counts(primary),
        "surface_reference": _face_counts(reference),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part_id", nargs="?", default="component-simplify")
    parser.add_argument("--json", action="store_true", help="emit the complete report as JSON")
    args = parser.parse_args()
    report = collect_baseline(args.part_id)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"part_id: {report['part_id']}")
        for input_record in report["raw_inputs"]:
            print(f"{input_record['role']} SHA-256: {input_record['sha256']}")
        print("primary_model: {faces} faces, {planar_faces} planar".format(**report["primary_model"]))
        print("surface_reference: {faces} faces, {planar_faces} planar".format(**report["surface_reference"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
