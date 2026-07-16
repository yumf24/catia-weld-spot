"""Smoke-check the weld-core environment (Mac / cross-platform).

Run:  python scripts/check_env_core.py
Verifies numpy + pydantic + weld_core import and a schema round-trip works.
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        import numpy  # noqa: F401
        import pydantic  # noqa: F401
        from weld_core import __version__
        from weld_core.schema import FacesDocument, FaceRecord

        doc = FacesDocument(faces=[FaceRecord(id="b/face_1", part="P", body="b")])
        assert FacesDocument.model_validate_json(doc.model_dump_json()).faces[0].id == "b/face_1"
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] core env check: {exc}")
        return 1

    print(f"[OK] weld-core env ready (weld_core {__version__})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
