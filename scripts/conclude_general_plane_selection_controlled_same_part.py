"""Publish the managed offline conclusion for the controlled same-part search."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.controlled_same_part_policy import (  # noqa: E402
    build_controlled_same_part_conclusion,
    render_controlled_same_part_conclusion_markdown,
)
from weld_core.data_layout import DATA_ROOT, find_run, register_managed_artifact  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish an offline controlled same-part conclusion.")
    parser.add_argument("part_id")
    parser.add_argument("--run-dir", help="Managed run directory containing the topology diagnosis and policy search.")
    args = parser.parse_args(argv)
    try:
        run_dir = Path(args.run_dir) if args.run_dir else find_run(args.part_id, root=DATA_ROOT)
        topology = json.loads((run_dir / "general_plane_selection_same_part_topology_diagnosis.json").read_text(encoding="utf-8"))
        search = json.loads((run_dir / "general_plane_selection_controlled_pair_policy_search.json").read_text(encoding="utf-8"))
        report = build_controlled_same_part_conclusion(topology, search)
        report.update({"part_id": args.part_id, "run_id": json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["run_id"]})
        json_path = run_dir / "general_plane_selection_controlled_same_part_conclusion.json"
        markdown_path = run_dir / "general_plane_selection_controlled_same_part_conclusion.md"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        markdown_path.write_text(render_controlled_same_part_conclusion_markdown(report), encoding="utf-8")
        register_managed_artifact(json_path, "general_plane_selection_controlled_same_part_conclusion", kind="json")
        register_managed_artifact(markdown_path, "general_plane_selection_controlled_same_part_conclusion_markdown", kind="markdown")
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"wrote offline controlled same-part conclusion -> {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
