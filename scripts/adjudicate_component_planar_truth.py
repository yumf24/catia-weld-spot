"""Create evaluation-only planar support adjudication for a component run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from extract_ground_truth import extract_ground_truth  # noqa: E402
from weld_core.data_layout import register_artifact, sha256_file, update_run_manifest  # noqa: E402
from weld_core.general_plane_selection import general_faces_from_step_groups  # noqa: E402
from weld_core.planar_truth_adjudication import adjudicate_planar_truth, adjudication_markdown  # noqa: E402
from weld_core.step_geometry import parse_step_faces  # noqa: E402


def _latest_run() -> Path:
    parent = REPO_ROOT / "data" / "component-weld-evaluation"
    runs = sorted(path for path in parent.iterdir() if path.is_dir() and (path / "manifest.json").is_file())
    if not runs:
        raise argparse.ArgumentTypeError("no completed component-weld-evaluation run exists")
    return runs[-1]


def _run_dir(value: str) -> Path:
    path = Path(value).resolve()
    if path.parent.name != "component-weld-evaluation" or not (path / "manifest.json").is_file() or not (path / "candidates.json").is_file():
        raise argparse.ArgumentTypeError("run directory must be a completed component-weld-evaluation run")
    return path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-dir", type=_run_dir)
    group.add_argument("--latest-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        run_dir = _latest_run() if args.latest_run else args.run_dir
        _run_dir(str(run_dir))
        truth = extract_ground_truth(str(REPO_ROOT / "raw_data" / "component" / "SPOT.step"))
        faces = general_faces_from_step_groups(parse_step_faces(str(REPO_ROOT / "raw_data" / "component" / "component.step")))
        report = adjudicate_planar_truth(truth.points, faces)
        if report["summary"]["ground_truth_count"] != 286:
            raise RuntimeError("expected exactly 286 registered ground-truth points")
        json_path = run_dir / "planar_truth_adjudication.json"
        md_path = run_dir / "planar_truth_adjudication.md"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        md_path.write_text(adjudication_markdown(report), encoding="utf-8")
        register_artifact(run_dir, "planar_truth_adjudication", json_path, kind="json", sha256=sha256_file(json_path), count=286)
        register_artifact(run_dir, "planar_truth_adjudication_markdown", md_path, kind="markdown", sha256=sha256_file(md_path))
        update_run_manifest(run_dir, planar_truth_adjudication={"scope": report["scope"], "summary": report["summary"]})
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] planar truth adjudication -> {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
