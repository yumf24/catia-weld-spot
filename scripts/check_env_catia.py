"""Smoke-check the weld-catia environment (Windows, CATIA V5 running).

Run on the Windows machine, with CATIA V5 open:
    python scripts/check_env_catia.py

Verifies pywin32 + pycatia import and that we can connect to a running
CATIA session. This is the Phase 0 CATIA-side acceptance gate.
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        import win32com  # noqa: F401  (pywin32)
        from pycatia import catia
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] import pycatia/pywin32: {exc}")
        print("       Install with: pip install pycatia pywin32")
        return 1

    try:
        app = catia()  # connects to the running CATIA.Application COM object
        name = app.name
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] connect to CATIA: {exc}")
        print("       Ensure CATIA V5 is running. If COM is unregistered, run")
        print("       `cnext.exe /regserver` from the CATIA bin directory.")
        return 1

    print(f"[OK] connected to CATIA application: {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
