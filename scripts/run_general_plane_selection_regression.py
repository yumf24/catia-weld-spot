from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from weld_core.data_layout import DataLayoutError
from weld_core.general_plane_selection import GeneralSelectionParams, run_registered_general_plane_selection
from weld_core.pipeline import main as pipeline_main

from evaluate_general_plane_selection import main as evaluation_main  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run generic plane selection, offline reference evaluation, and candidate generation for one registered part."
    )
    parser.add_argument("part_id")
    parser.add_argument("--run-label", default="generic-regression")
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
        evaluation_code = evaluation_main([args.part_id, "--run-dir", str(run_dir)])
        if evaluation_code != 0:
            return evaluation_code
        candidates_code = pipeline_main([str(run_dir / "faces.general-selected.json"), str(run_dir / "candidates.json")])
        if candidates_code != 0:
            return candidates_code
    except (DataLayoutError, OSError, RuntimeError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"wrote generic regression run -> {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
