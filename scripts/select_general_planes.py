from __future__ import annotations

import argparse
import sys

from weld_core.data_layout import DataLayoutError
from weld_core.general_plane_selection import GeneralSelectionParams, run_registered_general_plane_selection


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select generic planar weld faces from a registered primary STEP input.")
    parser.add_argument("part_id")
    parser.add_argument("--run-label", default="generic-selection")
    parser.add_argument("--max-normal-angle-deg", type=float, default=GeneralSelectionParams.max_normal_angle_deg)
    parser.add_argument("--max-plane-gap-mm", type=float, default=GeneralSelectionParams.max_plane_gap_mm)
    parser.add_argument("--min-overlap-area-mm2", type=float, default=GeneralSelectionParams.min_overlap_area_mm2)
    parser.add_argument("--min-face-coverage", type=float, default=GeneralSelectionParams.min_face_coverage)
    parser.add_argument("--min-effective-width-mm", type=float, default=GeneralSelectionParams.min_effective_width_mm)
    parser.add_argument("--allow-same-part-pairs", action="store_true")
    args = parser.parse_args(argv)

    params = GeneralSelectionParams(
        max_normal_angle_deg=args.max_normal_angle_deg,
        max_plane_gap_mm=args.max_plane_gap_mm,
        min_overlap_area_mm2=args.min_overlap_area_mm2,
        min_face_coverage=args.min_face_coverage,
        min_effective_width_mm=args.min_effective_width_mm,
        allow_same_part_pairs=args.allow_same_part_pairs,
    )
    try:
        run_dir = run_registered_general_plane_selection(args.part_id, run_label=args.run_label, params=params)
    except (DataLayoutError, OSError, RuntimeError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"wrote generic plane selection run -> {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
