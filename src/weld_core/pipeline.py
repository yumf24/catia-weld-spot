"""Pipeline orchestration: faces.json -> candidates.json.

Usage:
    python -m weld_core.pipeline <faces.json> [candidates.json]
"""

from __future__ import annotations

import json
import sys
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


def run(
    faces_doc: FacesDocument, params: WeldParams | None = None, *, provenance: dict[str, str] | None = None
) -> CandidatesDocument:
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
        meta=CandidatesMeta(source=faces_doc.meta.part, params=params.as_dict(), **(provenance or {})),
        candidates=candidates,
    )


def _template_provenance(faces_path: Path) -> dict[str, str] | None:
    """Require the frozen selected-face artifact for component-simplify runs."""
    manifest_path = faces_path.parent / "manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("part_id") != "component-simplify":
        return None
    selected = manifest.get("artifacts", {}).get("selected_faces", {})
    if selected.get("path") != faces_path.name or faces_path.name != "faces.selected.json":
        raise ValueError("component-simplify requires the managed faces.selected.json frozen-template artifact")
    parameters = manifest.get("parameters", {})
    primary = next((item for item in manifest.get("raw_inputs", []) if item.get("role") == "primary_model"), None)
    if not primary or not parameters.get("template_sha256"):
        raise ValueError("component-simplify run is missing primary STEP or frozen-template provenance")
    return {
        "selected_faces_source": str(faces_path.name),
        "template_sha256": parameters["template_sha256"],
        "primary_step_sha256": primary["sha256"],
    }


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    faces_path = Path(argv[0])
    out_path = Path(argv[1]) if len(argv) > 1 else faces_path.with_name("candidates.json")
    try:
        provenance = _template_provenance(faces_path)
        doc = run(load_faces(faces_path), provenance=provenance)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    dump_document(doc, out_path)
    if provenance is not None:
        from .data_layout import register_managed_artifact
        register_managed_artifact(out_path, "candidates", selected_faces_source=provenance["selected_faces_source"],
                                  template_sha256=provenance["template_sha256"], primary_step_sha256=provenance["primary_step_sha256"])
    print(f"wrote {len(doc.candidates)} candidates -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
