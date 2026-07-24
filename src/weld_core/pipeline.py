"""Pipeline orchestration: faces.json -> candidates.json.

Usage:
    python -m weld_core.pipeline <faces.json> [candidates.json]
"""

from __future__ import annotations

import sys
import json
from pathlib import Path

from .config import WeldParams
from .filtering import filter_candidates
from .pairing import find_mating_pairs
from .points import layout_points
from .region import build_region
from .schema import (
    CandidatesDocument,
    CandidatesMeta,
    FacesDocument,
    dump_document,
    load_faces,
)


def run(faces_doc: FacesDocument, params: WeldParams | None = None) -> CandidatesDocument:
    params = params or WeldParams()

    eligible = [
        f
        for f in faces_doc.faces
        if f.surface_type == "planar" and not f.manual_review and f.vertices
    ]
    pairs = find_mating_pairs(eligible, params)

    candidates = []
    for face_a, face_b in pairs:
        region = build_region(face_a, face_b, params)
        if region is None:
            continue
        candidates.extend(layout_points(region, params))

    candidates = filter_candidates(candidates, params)

    # Sort by content (face-pair identity, then position) rather than
    # discovery order before numbering. Pair discovery order comes from the
    # input faces list order, which is not guaranteed stable across
    # independent CATIA extractions of the same document (see DEVLOG.md) --
    # numbering by discovery order let the same physical candidate get a
    # different wc_NNN id across runs, which silently corrupted
    # catia/write_candidates.py's id-based update-in-place matching.
    candidates.sort(key=lambda c: (tuple(sorted(c.faces)), c.position))
    for i, c in enumerate(candidates, start=1):
        c.id = f"wc_{i:03d}"

    return CandidatesDocument(
        meta=CandidatesMeta(source=faces_doc.meta.part, params=params.as_dict()),
        candidates=candidates,
    )


def _infer_general_selection_source(faces_path: Path) -> dict:
    if faces_path.name != "faces.general-selected.json":
        return {}
    run_dir = faces_path.resolve().parent
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        return {"kind": "general_planar_selection", "faces_artifact": faces_path.name}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"kind": "general_planar_selection", "faces_artifact": faces_path.name}
    artifacts = manifest.get("artifacts", {})
    if "faces.general-selected" not in artifacts:
        return {}
    return {
        "kind": "general_planar_selection",
        "part_id": manifest.get("part_id", ""),
        "run_id": manifest.get("run_id", ""),
        "faces_artifact": "faces.general-selected",
        "parameters": manifest.get("parameters", {}).get("general_selection", {}),
    }


def _layout_registered_exact_regions(run_dir: Path, params: WeldParams):
    """Generate candidates from registered exact regions, never their AABBs."""

    from .candidate_merging import safe_merge_candidates
    from .coverage_layout import layout_exact_region, read_exact_region
    from .multilayer_candidates import aggregate_multilayer_candidates

    audit_path = run_dir / "interface_region_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    candidates = []
    layout_audit = []
    for record in audit.get("regions", []):
        region = read_exact_region(record, run_dir)
        laid_out, result = layout_exact_region(region, params)
        for candidate in laid_out:
            candidate.exact_region_refs = [record["geometry_ref"]]
        candidates.extend(laid_out)
        layout_audit.append({
            "interface_id": result.interface_id,
            "coverage_radius_mm": result.coverage_radius_mm,
            "grid_pitch_mm": result.grid_pitch_mm,
            "generated_count": result.generated_count,
            "retained_count": result.retained_count,
            "rejected_outside_exact_region": result.rejected_outside_exact_region,
        })
    original_layout_points = [
        {
            "candidate_id": candidate.id,
            "position_mm": list(candidate.position),
            "source_interfaces": candidate.supporting_interfaces,
            "status": "retained_for_physical_stationing",
            "reason": "inside_exact_region",
        }
        for candidate in candidates
    ]
    candidates, merge_audit = safe_merge_candidates(candidates, params)
    candidates, multilayer_audit = aggregate_multilayer_candidates(candidates, params)
    final_candidates = [
        {
            "candidate_id": candidate.id,
            "source_candidate_ids": next(
                (row["source_candidate_ids"] for row in multilayer_audit if row["representative_candidate_id"] == candidate.id),
                [candidate.id],
            ),
            "position_mm": list(candidate.position),
            "source_interfaces": candidate.supporting_interfaces,
            "status": "selected",
            "reason": "physical_station_retained",
        }
        for candidate in candidates
    ]
    return candidates, {
        "format_version": 2,
        "parameters": {
            "coverage_radius_mm": params.coverage_radius_mm,
            "coincident_merge_tolerance_mm": params.coincident_merge_tolerance_mm,
        },
        "interfaces": layout_audit,
        "original_exact_layout_points": original_layout_points,
        "physical_stations": multilayer_audit,
        "final_candidates": final_candidates,
        "merges": merge_audit,
        "multilayer_groups": multilayer_audit,
    }


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    faces_path = Path(argv[0])
    out_path = Path(argv[1]) if len(argv) > 1 else faces_path.with_name("candidates.json")
    try:
        faces_doc = load_faces(faces_path)
        exact_audit = faces_path.parent / "interface_region_audit.json"
        if faces_path.name == "faces.general-selected.json" and exact_audit.is_file():
            candidates, layout_audit = _layout_registered_exact_regions(faces_path.parent, WeldParams())
            candidates.sort(key=lambda candidate: (tuple(sorted(candidate.faces)), candidate.position))
            candidate_ids = {}
            for index, candidate in enumerate(candidates, start=1):
                original_id = candidate.id
                candidate.id = f"wc_{index:03d}"
                candidate_ids[original_id] = candidate.id
            for row in layout_audit["final_candidates"]:
                row["candidate_id"] = candidate_ids[row["candidate_id"]]
            doc = CandidatesDocument(
                meta=CandidatesMeta(source=faces_doc.meta.part, params=WeldParams().as_dict()),
                candidates=candidates,
            )
            (faces_path.parent / "coverage_layout_audit.json").write_text(
                json.dumps(layout_audit, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        else:
            doc = run(faces_doc)
    except (OSError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    doc.meta.selection_source = _infer_general_selection_source(faces_path)
    dump_document(doc, out_path)
    from .data_layout import register_managed_artifact
    register_managed_artifact(out_path, "candidates")
    if faces_path.name == "faces.general-selected.json" and (faces_path.parent / "coverage_layout_audit.json").is_file():
        register_managed_artifact(faces_path.parent / "coverage_layout_audit.json", "coverage_layout_audit")
    print(f"wrote {len(doc.candidates)} candidates -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
