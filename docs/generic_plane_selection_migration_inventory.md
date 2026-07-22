# Generic Plane Selection Migration Inventory

Created: 2026-07-22 16:01:19 +08:00

This inventory completes G01 of `docs/ALG_updatev2.json`. It records the
current frozen-template implementation as a migration baseline only. It does
not change algorithm behavior.

## Clean Baseline

- `git status --short`: clean before G01 work.
- `.venv\Scripts\python -m pytest --basetemp .pytest_cache\g01-full`: 72 passed.
- `.venv\Scripts\python scripts\check_plane_selection_baseline.py component-simplify`:
  - primary STEP: 2834 faces, 525 planar faces.
  - reference STEP: 89 faces, 40 planar faces.

The component-simplify counts above are dataset regression facts. They must
not be promoted into production constants, branching conditions, default
thresholds, identity checks, or generalization claims.

## Frozen Template Removal Scope

The following current runtime paths and symbols are specific to the frozen
component-simplify route and are planned for removal or replacement by the
generic selection flow in later steps:

- `templates/component-simplify/plane-selection-template.json`
- `scripts/build_plane_selection_template.py`
- `scripts/select_template_planes.py`
- `scripts/evaluate_template_plane_selection.py`
- `src/weld_core/template_plane_selection.py`
- `src/weld_core/pipeline.py` checks that require
  `component-simplify`, `faces.selected.json`, registered template provenance,
  `template_sha256`, or primary STEP SHA provenance for production behavior.
- `src/weld_core/schema.py` candidate metadata fields that expose frozen
  template provenance: `selected_faces_source`, `template_sha256`, and
  `primary_step_sha256`.
- Tests dedicated to the frozen template route:
  `tests/test_plane_selection_template.py`,
  `tests/test_template_plane_selection.py`, and frozen-template assertions in
  `tests/test_pipeline.py`.
- Current documentation sections in `CLI.md` and `docs/json_contract.md` that
  describe template building, template selection, template evaluation,
  `faces.selected.json`, template SHA checks, or component-simplify-only
  pipeline requirements.
- Managed run artifacts that represent historical runs only:
  `faces.selected.json`, `selection_audit.json`, template-evaluation reports,
  and candidate metadata containing template provenance.

## Generic Geometry To Retain

The following capabilities are general and should be preserved, moved, or
reused while removing the frozen path:

- STEP parsing and CAD face grouping in `src/weld_core/step_geometry.py`.
- Exact CAD face overlap and coverage calculations in
  `src/weld_core/exact_face_overlap.py`.
- Plane, normal, distance, bbox, and vector utilities used by pairing and
  validation modules.
- Run manifest helpers and raw-data manifest integrity checks, provided they
  validate only the declared runtime input rather than selecting behavior by
  dataset identity.
- General `FacesDocument` and downstream candidate generation semantics that
  accept arbitrary face documents.

## Historical Interpretation

The frozen template achieved a component-simplify regression result of 40 TP,
0 FP, and 0 FN in prior runs. That result is a historical measurement for one
dataset. It is not evidence that the current production selection logic
generalizes to unknown parts, and it must not be used to hard-code runtime
face identity, STEP index, known face counts, part names, fingerprints, or
input SHA-specific selection behavior.
