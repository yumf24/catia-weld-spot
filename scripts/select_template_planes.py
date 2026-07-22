"""Select primary STEP planes from a frozen template without opening the reference STEP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.data_layout import create_run, load_raw_manifest, sha256_file, register_artifact, update_run_manifest  # noqa: E402
from weld_core.schema import dump_document  # noqa: E402
from weld_core.step_geometry import parse_step_faces  # noqa: E402
from weld_core.template_plane_selection import (  # noqa: E402
    TemplateSelectionError, load_template, select_template_planes, template_sha256,
    validate_primary_sha,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part_id")
    parser.add_argument("--run-label", default="template-selection")
    parser.add_argument("--template", type=Path)
    args = parser.parse_args()
    template_path = args.template or REPO_ROOT / "templates" / args.part_id / "plane-selection-template.json"
    try:
        template = load_template(template_path)
        if template["part_id"] != args.part_id:
            raise TemplateSelectionError("template part_id does not match requested part-id")
        raw_manifest = load_raw_manifest(args.part_id)
        primary = REPO_ROOT / "raw_data" / args.part_id / raw_manifest["inputs"]["primary_model"]["path"]
        primary_sha = sha256_file(primary)
        validate_primary_sha(template, primary_sha)
        # Creating the managed run verifies only primary_model.  Do not use
        # verify_raw_inputs() without roles here: that would read the forbidden
        # surface_reference during normal runtime selection.
        run_dir, _manifest = create_run(
            args.part_id, args.run_label,
            parameters={"template_path": str(template_path), "template_sha256": template_sha256(template_path)},
            input_roles=("primary_model",),
        )
        faces, audit = select_template_planes(template, parse_step_faces(str(primary)))
        faces_path = run_dir / "faces.selected.json"
        audit_path = run_dir / "selection_audit.json"
        dump_document(faces, faces_path)
        audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        register_artifact(run_dir, "selected_faces", faces_path, face_count=len(faces.faces))
        register_artifact(run_dir, "selection_audit", audit_path, selected_faces=len(faces.faces))
        update_run_manifest(run_dir, status="completed")
        print(f"selected {len(faces.faces)} faces -> {run_dir}")
        return 0
    except (TemplateSelectionError, KeyError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
