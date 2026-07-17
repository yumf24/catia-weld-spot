"""Phase 4 helper: export the active CATIA document to STEP via COM.

Run on Windows with CATIA V5 running and the target Product/Part document
active:

    python catia/export_step.py output/component.stp

This is the ``Document.ExportData`` call that Phase 1.5/3 (see DEVLOG.md) used
ad hoc from a `python -c` one-liner to produce the STEP files consumed by
``scripts/enrich_faces_with_step.py``. Promoted to a standalone script here so
the full extract -> export -> enrich -> pipeline -> write chain can be driven
without a manual step (see ``scripts/run_full_pipeline.py``).

Notes from real-machine validation (see DEVLOG.md):
- Only the ``.stp`` extension + ``"stp"`` format string combination has been
  verified to work in this CATIA/pycatia setup. ``.step``/``"step"`` raised a
  generic COM error every time it was tried. This script hard-codes ``.stp``
  rather than exposing the format as a CLI option.
"""

from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pycatia import catia

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
STEP_FORMAT = "stp"


@dataclass
class RunStats:
    document: str = ""
    output_path: str = ""
    export_seconds: float = 0.0


def _safe_name(name: str) -> str:
    stem = Path(name).stem or name
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", stem) or "doc"


def write_run_log(stats: RunStats) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"export_step_{_safe_name(stats.document)}_{stamp}.log"

    lines = [
        "Weld-pipeline STEP export — run log",
        "=" * 48,
        f"{'timestamp':<22}: {datetime.now().isoformat(timespec='seconds')}",
        f"{'document':<22}: {stats.document}",
        f"{'output':<22}: {stats.output_path}",
        f"{'export time':<22}: {stats.export_seconds:.3f} s",
    ]
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log_path


def export_step(app, output: Path) -> RunStats:
    ad = app.active_document
    # CATIA's ExportData COM call fails outright on a relative path (pycatia
    # only logs a warning and passes it through as-is) -- verified on this
    # machine: a relative path raises a generic com_error, an absolute one
    # works.
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    ad.export_data(output, STEP_FORMAT, overwrite=True)
    elapsed = time.perf_counter() - start

    return RunStats(document=ad.name, output_path=str(output), export_seconds=elapsed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="path to write the STEP (.stp) file")
    args = parser.parse_args()

    app = catia()
    stats = export_step(app, args.output)
    log_path = write_run_log(stats)

    print(f"[OK] exported {stats.document} -> {stats.output_path} ({stats.export_seconds:.1f}s)")
    print(f"[PERF] log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
