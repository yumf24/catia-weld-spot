"""Build the evaluation-only causal candidate-chain atlas for one run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.candidate_chain_atlas import (  # noqa: E402
    CandidateChainAtlasError,
    build_candidate_chain_atlas,
    candidate_chain_atlas_markdown,
    load_selected_pair_audit,
    supporting_interface_ids,
)
from weld_core.data_layout import register_managed_artifact, sha256_file  # noqa: E402
from weld_core.schema import load_candidates  # noqa: E402


def _run_dir(value: str) -> Path:
    path = Path(value)
    if not path.is_dir():
        raise argparse.ArgumentTypeError("run directory must exist")
    return path


def _latest_run() -> Path:
    parent = REPO_ROOT / "data" / "component-weld-evaluation"
    runs = sorted(path for path in parent.iterdir() if path.is_dir())
    if not runs:
        raise CandidateChainAtlasError("no component-weld-evaluation run exists")
    return runs[-1]


def _read_json(run_dir: Path, name: str) -> dict:
    path = run_dir / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateChainAtlasError(f"cannot read {path}: {exc}") from exc


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-dir", type=_run_dir)
    group.add_argument("--latest-run", action="store_true")
    args = parser.parse_args(argv)
    run_dir = (_latest_run() if args.latest_run else args.run_dir).resolve()
    try:
        adjudication = _read_json(run_dir, "planar_truth_adjudication.json")
        atlas = build_candidate_chain_atlas(
            candidates=load_candidates(run_dir / "candidates.json"),
            adjudication=adjudication,
            evaluation=_read_json(run_dir, "weld_point_evaluation.json"),
            error_analysis=_read_json(run_dir, "weld_point_error_analysis.json"),
            pair_records=load_selected_pair_audit(
                run_dir / "pair_audit.json", supporting_interface_ids(adjudication),
            ),
            interface_region_audit=_read_json(run_dir, "interface_region_audit.json"),
            coverage_layout_audit=_read_json(run_dir, "coverage_layout_audit.json"),
            candidate_budget_audit=_read_json(run_dir, "candidate_budget_audit.json"),
        )
        json_path = run_dir / "candidate_chain_atlas.json"
        markdown_path = run_dir / "candidate_chain_atlas.md"
        json_path.write_text(json.dumps(atlas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        markdown_path.write_text(candidate_chain_atlas_markdown(atlas), encoding="utf-8")
        register_managed_artifact(json_path, "candidate_chain_atlas", kind="json", sha256=sha256_file(json_path))
        register_managed_artifact(markdown_path, "candidate_chain_atlas_markdown", kind="markdown", sha256=sha256_file(markdown_path))
    except (OSError, ValueError, CandidateChainAtlasError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] evaluation-only candidate-chain atlas -> {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
