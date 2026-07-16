"""Pipeline orchestration: faces.json -> candidates.json.

Phase 0 provides a runnable skeleton: it loads and validates the input,
threads the tunable params through, and writes a well-formed (currently
empty) candidates document. Phase 2 fills in pairing/region/points/filter.

Usage:
    python -m weld_core.pipeline <faces.json> [candidates.json]
"""

from __future__ import annotations

import sys
from pathlib import Path

from .config import WeldParams
from .schema import (
    CandidatesDocument,
    CandidatesMeta,
    FacesDocument,
    dump_document,
    load_faces,
)


def run(faces_doc: FacesDocument, params: WeldParams | None = None) -> CandidatesDocument:
    params = params or WeldParams()
    candidates: list = []

    # TODO(Phase 2): wire up the algorithm.
    #   planar = [f for f in faces_doc.faces if f.surface_type == "planar"
    #             and not f.manual_review]
    #   pairs = find_mating_pairs(planar, params)
    #   for a, b in pairs:
    #       region = build_region(a, b)
    #       candidates += filter_candidates(layout_points(region, params), params)

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
    doc = run(load_faces(faces_path))
    dump_document(doc, out_path)
    print(f"wrote {len(doc.candidates)} candidates -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
