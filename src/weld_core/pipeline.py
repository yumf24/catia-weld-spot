"""Pipeline orchestration: faces.json -> candidates.json.

Usage:
    python -m weld_core.pipeline <faces.json> [candidates.json]
"""

from __future__ import annotations

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


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    faces_path = Path(argv[0])
    out_path = Path(argv[1]) if len(argv) > 1 else faces_path.with_name("candidates.json")
    try:
        doc = run(load_faces(faces_path))
    except (OSError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    dump_document(doc, out_path)
    from .data_layout import register_managed_artifact
    register_managed_artifact(out_path, "candidates")
    print(f"wrote {len(doc.candidates)} candidates -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
