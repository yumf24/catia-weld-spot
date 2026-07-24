"""Evaluate one completed component candidate run against SPOT marker centers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from extract_ground_truth import extract_ground_truth  # noqa: E402
from weld_core.component_weld_point_evaluation import (  # noqa: E402
    error_analysis_markdown,
    enrich_with_planar_adjudication,
    evaluate_component_weld_points,
    evaluation_markdown,
)
from weld_core.data_layout import register_artifact, sha256_file, update_run_manifest  # noqa: E402
from weld_core.schema import dump_document, load_candidates  # noqa: E402


def _run_dir(value: str) -> Path:
    path = Path(value)
    if not (path / "manifest.json").is_file() or not (path / "candidates.json").is_file():
        raise argparse.ArgumentTypeError("run directory must contain manifest.json and candidates.json")
    return path


def _latest_run() -> Path:
    parent = REPO_ROOT / "data" / "component-weld-evaluation"
    runs = sorted(path for path in parent.iterdir() if path.is_dir() and (path / "manifest.json").is_file())
    if not runs:
        raise argparse.ArgumentTypeError("no component-weld-evaluation run exists")
    return runs[-1]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("run_dir", nargs="?", type=_run_dir, help="completed candidate run under data/component-weld-evaluation")
    group.add_argument("--latest-run", action="store_true")
    args = parser.parse_args(argv)
    run_dir = (_latest_run() if args.latest_run else args.run_dir).resolve()
    if run_dir.parent.name != "component-weld-evaluation":
        parser.error("run directory must be directly under data/component-weld-evaluation")
    try:
        candidates_path = run_dir / "candidates.json"
        truth_path = run_dir / "ground_truth.json"
        truth = extract_ground_truth(str(REPO_ROOT / "raw_data" / "component" / "SPOT.step"))
        dump_document(truth, truth_path)
        report, analysis = evaluate_component_weld_points(truth, load_candidates(candidates_path))
        adjudication_path = run_dir / "planar_truth_adjudication.json"
        if adjudication_path.is_file():
            candidate_audit_path = run_dir / "coverage_layout_audit.json"
            enrich_with_planar_adjudication(
                report, analysis, json.loads(adjudication_path.read_text(encoding="utf-8")), load_candidates(candidates_path),
                json.loads(candidate_audit_path.read_text(encoding="utf-8")) if candidate_audit_path.is_file() else None,
            )
        outputs = {
            "weld_point_evaluation.json": report,
            "weld_point_error_analysis.json": analysis,
        }
        for name, payload in outputs.items():
            (run_dir / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (run_dir / "weld_point_evaluation.md").write_text(evaluation_markdown(report), encoding="utf-8")
        (run_dir / "weld_point_error_analysis.md").write_text(error_analysis_markdown(analysis), encoding="utf-8")
        for name, kind in (("ground_truth", "json"), ("weld_point_evaluation", "json"), ("weld_point_evaluation_markdown", "markdown"), ("weld_point_error_analysis", "json"), ("weld_point_error_analysis_markdown", "markdown")):
            suffix = ".md" if kind == "markdown" else ".json"
            path = run_dir / ("ground_truth.json" if name == "ground_truth" else name.replace("_markdown", "") + suffix)
            register_artifact(run_dir, name, path, kind=kind, sha256=sha256_file(path))
        update_run_manifest(run_dir, evaluation={"ground_truth_markers": "raw_data/component/SPOT.step", "matching": report["matching"], "primary_tolerance_mm": report["primary_tolerance_mm"]})
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] component weld point evaluation -> {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
