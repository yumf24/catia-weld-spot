"""Phase 3: write candidates.json into CATIA as a Weld_Candidates point collection.

Run on Windows with CATIA V5 running and the target assembly (e.g. the
component.CATProduct this project has been working against) active:

    python catia/write_candidates.py <candidates.json>

Creates (first run) or reuses (subsequent runs) a top-level "Weld_Candidates"
Part component in the active document's root product, containing a
"Weld_Candidates" geometrical set with one point per candidate. Each point is
named after its candidate id (e.g. "wc_001") and carries a companion string
parameter with the metadata PLAN.md's output spec calls for (associated
faces, layer_type, spacing, generation reason) that doesn't fit naturally
into the point geometry itself.

Notes from real-machine validation (see DEVLOG.md):
- ``Products.add_new_component("Part", name)`` places the new component at
  the root product's origin with an identity placement matrix (verified via
  ``component.position.get_components()``) -- so the new Part's local frame
  equals the root product's global frame, matching how candidate positions
  were computed (Product-level GetMeasurableInContext / STEP global
  coordinates throughout this pipeline). This is checked defensively at
  runtime rather than assumed.
- **Re-running does NOT delete and recreate anything.** Two delete-based
  approaches were tried and both proved unreliable in this CATIA/pycatia
  setup: ``Selection.Delete()`` fails with a bare COM error, and
  ``Products.remove()`` + ``Document.close()`` silently leaves the
  underlying document referenced/reused rather than truly freed, so old
  geometry keeps accumulating across runs instead of being replaced.
  Instead, re-runs reuse the same "Weld_Candidates" part/body and *update
  points in place*: a point's real geometric position is driven by its
  auto-generated ``<body>\\<point>\\X``/``Y``/``Z`` parameters, and setting
  those parameter values directly moves the point (verified: reading the
  point's position back through the typed ``HybridShapePointCoord.x/y/z``
  API after the edit shows the new value, not the original). Candidates
  missing from a smaller subsequent run are left in place but tagged stale
  via their info parameter rather than deleted, since deletion is what
  proved unreliable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pycatia import catia

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from weld_core.schema import Candidate, load_candidates  # noqa: E402
from weld_core.production_truth_isolation import assert_production_read_path  # noqa: E402

COMPONENT_NAME = "Weld_Candidates"
BODY_NAME = "Weld_Candidates"
IDENTITY_PLACEMENT = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)
STALE_PREFIX = "STALE - not present in latest run: "


def _find_index_by_part_number(products, name: str) -> int | None:
    for i in range(1, products.count + 1):
        if products.item(i).part_number == name:
            return i
    return None


def _check_identity_placement(component) -> None:
    placement = tuple(round(c, 9) for c in component.position.get_components())
    if placement != IDENTITY_PLACEMENT:
        raise RuntimeError(
            f"{COMPONENT_NAME} component is not at identity placement "
            f"(got {placement}); candidate positions assume the part's local "
            "frame equals the root product's global frame -- refusing to write "
            "points that would end up in the wrong place"
        )


def get_or_create_weld_part(app, root_product):
    """Find the existing "Weld_Candidates" Part, or create it if absent.

    Reuses the same part across runs (see module docstring for why this
    project doesn't delete-and-recreate it).
    """
    products = root_product.products
    existing_idx = _find_index_by_part_number(products, COMPONENT_NAME)
    if existing_idx is not None:
        component = products.item(existing_idx)
    else:
        component = products.add_new_component("Part", COMPONENT_NAME)

    _check_identity_placement(component)

    weld_doc = app.documents.item(f"{COMPONENT_NAME}.CATPart")
    return weld_doc.part


def get_or_create_body(part):
    body = part.hybrid_bodies.get_item_by_name(BODY_NAME)
    if body is None:
        body = part.hybrid_bodies.add()
        body.name = BODY_NAME
    return body


def _candidate_info(c: Candidate) -> str:
    return (
        f"faces={','.join(c.faces)}; layer={c.layer_type}; "
        f"layer_count={c.layer_count}; interfaces={','.join(c.supporting_interfaces)}; "
        f"confidence={c.confidence_tier}; exact_regions={','.join(c.exact_region_refs)}; "
        f"spacing={c.spacing_mm:.2f}mm; reason={c.reason}"
    )


def _get_param(parameters, name: str):
    """Safe by-name parameter lookup.

    ``Parameters.get_item_by_name`` compares against the full qualified name
    (e.g. ``"Weld_Candidates\\wc_001_info"``), not the short name we create
    params with, so it never matches and always returns None -- silently
    causing duplicate ``create_string`` calls (verified: this produced
    ``wc_001_info`` + a stray ``wc_001_info.1`` on every point). The raw
    ``.item()`` call *does* resolve short names correctly, so use that,
    wrapped to turn its "not found" COM error into ``None``.
    """
    try:
        return parameters.item(name)
    except Exception:
        return None


def _update_point_position(part, point_name: str, position) -> None:
    for axis, value in zip("XYZ", position):
        param = part.parameters.item(f"{BODY_NAME}\\{point_name}\\{axis}")
        param.value = value


def write_candidates(part, body, candidates: list[Candidate]) -> tuple[int, int, int]:
    """Create new points / update existing ones in place. Returns (created, updated, staled)."""
    existing_names = {shape.name for shape in body.hybrid_shapes}
    new_ids = {c.id for c in candidates}

    part.in_work_object = body
    hsf = part.hybrid_shape_factory

    created = updated = 0
    for c in candidates:
        info = _candidate_info(c)
        if c.id in existing_names:
            _update_point_position(part, c.id, c.position)
            info_param = _get_param(part.parameters, f"{c.id}_info")
            if info_param is not None:
                info_param.value = info
            else:
                part.parameters.create_string(f"{c.id}_info", info)
            updated += 1
        else:
            point = hsf.add_new_point_coord(*c.position)
            body.append_hybrid_shape(point)
            point.name = c.id
            part.parameters.create_string(f"{c.id}_info", info)
            created += 1

    staled = 0
    for stale_name in existing_names - new_ids:
        info_param = _get_param(part.parameters, f"{stale_name}_info")
        if info_param is None:
            part.parameters.create_string(f"{stale_name}_info", STALE_PREFIX + "(no prior info)")
            staled += 1
        elif not info_param.value.startswith(STALE_PREFIX):
            info_param.value = STALE_PREFIX + info_param.value
            staled += 1

    part.update()
    return created, updated, staled


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates_json", type=Path, help="path to candidates.json")
    args = parser.parse_args()

    doc = load_candidates(assert_production_read_path(args.candidates_json))

    app = catia()
    ad = app.active_document
    root_product = ad.product

    part = get_or_create_weld_part(app, root_product)
    body = get_or_create_body(part)
    created, updated, staled = write_candidates(part, body, doc.candidates)

    print(
        f"[OK] {created} created, {updated} updated, {staled} newly marked stale "
        f"-> {COMPONENT_NAME} in {ad.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
