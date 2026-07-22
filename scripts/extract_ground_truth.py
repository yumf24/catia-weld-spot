"""Offline: parse a weld-spot marker STEP file into ground_truth.json.

Real weld points aren't tagged in the assembly's own geometry — they're
marked separately as small (r=3mm) ball geometry, one ball per real weld
point (see ``raw_data/component/SPOT.step`` and ``weld_core.step_geometry.
parse_step_spheres`` for how this was discovered/validated: 572 marker faces
collapse to 286 unique sphere centers, each typed ``GeomAbs_Sphere`` by
OCCT with ``radius == 3.0`` exactly).

This only reads a static STEP file via OCP — no CATIA/pycatia/pywin32, no
running CATIA session required. Run it directly with the project's ``.venv``:

    python scripts/extract_ground_truth.py raw_data/component/SPOT.step data/component/<run-id>/ground_truth.json

The output is a ``weld_core.schema.GroundTruthDocument`` — feed it to
``weld_core.evaluate`` alongside a ``candidates.json`` to score the pipeline
against these real weld points.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.schema import (  # noqa: E402
    GroundTruthDocument,
    GroundTruthMeta,
    GroundTruthPoint,
    dump_document,
)
from weld_core.data_layout import register_managed_artifact  # noqa: E402
from weld_core.step_geometry import parse_step_spheres  # noqa: E402


def extract_ground_truth(step_path: str) -> GroundTruthDocument:
    spheres = parse_step_spheres(step_path)
    points = [
        GroundTruthPoint(
            id=f"gt_{i:03d}",
            position=s.center,
            radius=s.radius,
            label=s.label,
        )
        for i, s in enumerate(sorted(spheres, key=lambda s: s.center), start=1)
    ]
    return GroundTruthDocument(
        meta=GroundTruthMeta(source=str(step_path)),
        points=points,
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step_path", type=Path, help="weld-spot marker STEP file, e.g. raw_data/component/SPOT.step")
    parser.add_argument("out", type=Path, nargs="?", default=None)
    args = parser.parse_args(argv)

    out_path = args.out or args.step_path.with_suffix(".ground_truth.json")

    doc = extract_ground_truth(str(args.step_path))
    dump_document(doc, out_path)
    register_managed_artifact(out_path, "ground_truth")
    print(f"[OK] {len(doc.points)} ground-truth weld points -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
