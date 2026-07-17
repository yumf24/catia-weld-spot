"""Phase 4 end-to-end orchestrator: active CATIA doc -> candidates.json (-> CATIA).

Chains the pipeline's existing, independently-validated stages instead of
reimplementing any of them (see DEVLOG.md for why each stage is built the way
it is):

    1. catia/extract_faces.py   (COM, active doc)      -> faces.json
    2. catia/export_step.py     (COM, active doc)       -> <prefix>.stp
    3. scripts/enrich_faces_with_step.py (offline, OCP)  -> faces.enriched.json
    4. weld_core.pipeline.run   (offline, pure Python)   -> candidates.json
    5. catia/write_candidates.py (COM, active doc, only with --write)

Run on Windows with CATIA V5 running and the target assembly active:

    python scripts/run_full_pipeline.py data/component_e2e [--write]
    python scripts/run_full_pipeline.py data/component_e2e --part-number NAME --limit 50

Produces, next to <prefix>:
    <prefix>.stp
    <prefix>.faces.json
    <prefix>.faces.enriched.json
    <prefix>.candidates.json
and a combined timing/result log under logs/.

``--write`` is opt-in: without it, this only reads from CATIA (extract +
export) and writes local JSON/STEP files, it does not touch the live
document. With it, the last stage reuses ``catia/write_candidates.py``'s
create-or-update-in-place logic against the active document's root product.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "catia"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pycatia import catia  # noqa: E402

import export_step as es  # noqa: E402
import extract_faces as ef  # noqa: E402
import write_candidates as wc  # noqa: E402
from enrich_faces_with_step import enrich_faces_document  # noqa: E402
from weld_core.config import WeldParams  # noqa: E402
from weld_core.pipeline import run as run_pipeline  # noqa: E402
from weld_core.schema import dump_document  # noqa: E402

LOG_DIR = REPO_ROOT / "logs"


@dataclass
class StageTimes:
    extract_seconds: float = 0.0
    export_seconds: float = 0.0
    enrich_seconds: float = 0.0
    core_seconds: float = 0.0
    write_seconds: float = 0.0


@dataclass
class RunResult:
    document: str = ""
    prefix: str = ""
    faces_total: int = 0
    faces_planar: int = 0
    faces_matched: int = 0
    candidates: int = 0
    write_created: int | None = None
    write_updated: int | None = None
    write_staled: int | None = None
    times: StageTimes = field(default_factory=StageTimes)
    total_seconds: float = 0.0


def _safe_name(name: str) -> str:
    stem = Path(name).stem or name
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", stem) or "doc"


def write_run_log(result: RunResult) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"run_full_pipeline_{_safe_name(result.document)}_{stamp}.log"

    t = result.times
    lines = [
        "Weld-pipeline full run (extract -> export -> enrich -> core -> write) — log",
        "=" * 48,
        f"{'timestamp':<22}: {datetime.now().isoformat(timespec='seconds')}",
        f"{'document':<22}: {result.document}",
        f"{'output prefix':<22}: {result.prefix}",
        "",
        "Timing",
        "-" * 48,
        f"{'extract (COM)':<22}: {t.extract_seconds:.3f} s",
        f"{'export STEP (COM)':<22}: {t.export_seconds:.3f} s",
        f"{'enrich (OCP)':<22}: {t.enrich_seconds:.3f} s",
        f"{'core (pure python)':<22}: {t.core_seconds:.3f} s",
        f"{'write (COM)':<22}: {t.write_seconds:.3f} s" if result.write_created is not None else
        f"{'write (COM)':<22}: skipped (--write not passed)",
        f"{'total':<22}: {result.total_seconds:.3f} s",
        "",
        "Volume",
        "-" * 48,
        f"{'faces (total)':<25}: {result.faces_total}",
        f"{'faces (planar)':<25}: {result.faces_planar}",
        f"{'faces (STEP-matched)':<25}: {result.faces_matched}",
        f"{'candidates':<25}: {result.candidates}",
    ]
    if result.write_created is not None:
        lines += [
            f"{'  created':<25}: {result.write_created}",
            f"{'  updated':<25}: {result.write_updated}",
            f"{'  newly stale':<25}: {result.write_staled}",
        ]
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix", type=Path, help="output path prefix, e.g. data/component_e2e")
    parser.add_argument(
        "--write",
        action="store_true",
        help="also write the resulting candidates back into the active CATIA document",
    )
    parser.add_argument("--part-number", default=None, help="passthrough to extract_faces")
    parser.add_argument("--limit", type=int, default=None, help="passthrough to extract_faces")
    args = parser.parse_args()

    prefix = args.prefix
    prefix.parent.mkdir(parents=True, exist_ok=True)
    step_path = prefix.with_suffix(".stp")
    faces_path = Path(f"{prefix}.faces.json")
    enriched_path = Path(f"{prefix}.faces.enriched.json")
    candidates_path = Path(f"{prefix}.candidates.json")

    run_start = time.perf_counter()
    times = StageTimes()

    app = catia()
    document_name = app.active_document.name

    print("[1/5] extracting faces from active document (COM)...")
    faces_doc, extract_stats = ef.extract_faces(app, args.part_number, args.limit)
    dump_document(faces_doc, faces_path)
    times.extract_seconds = extract_stats.total_seconds
    print(f"      {extract_stats.faces_processed} faces ({extract_stats.planar_count} planar)")

    print("[2/5] exporting active document to STEP (COM)...")
    export_stats = es.export_step(app, step_path)
    times.export_seconds = export_stats.export_seconds
    print(f"      -> {step_path} ({export_stats.export_seconds:.1f}s)")

    print("[3/5] enriching faces with STEP-derived vertices (offline)...")
    faces_doc, enrich_stats = enrich_faces_document(faces_doc, str(step_path))
    dump_document(faces_doc, enriched_path)
    times.enrich_seconds = enrich_stats.total_seconds
    enrich_totals = enrich_stats.totals
    print(f"      {enrich_totals.matched}/{enrich_totals.planar_com_faces} planar faces matched")

    print("[4/5] running weld_core pipeline (offline)...")
    core_start = time.perf_counter()
    candidates_doc = run_pipeline(faces_doc, WeldParams())
    times.core_seconds = time.perf_counter() - core_start
    dump_document(candidates_doc, candidates_path)
    print(f"      {len(candidates_doc.candidates)} candidates -> {candidates_path}")

    result = RunResult(
        document=document_name,
        prefix=str(prefix),
        faces_total=extract_stats.faces_processed,
        faces_planar=extract_stats.planar_count,
        faces_matched=enrich_totals.matched,
        candidates=len(candidates_doc.candidates),
        times=times,
    )

    if args.write:
        print("[5/5] writing candidates back into the active document (COM)...")
        write_start = time.perf_counter()
        root_product = app.active_document.product
        part = wc.get_or_create_weld_part(app, root_product)
        body = wc.get_or_create_body(part)
        created, updated, staled = wc.write_candidates(part, body, candidates_doc.candidates)
        times.write_seconds = time.perf_counter() - write_start
        result.write_created, result.write_updated, result.write_staled = created, updated, staled
        print(f"      {created} created, {updated} updated, {staled} newly marked stale")
    else:
        print("[5/5] skipped (pass --write to write candidates back into CATIA)")

    result.total_seconds = time.perf_counter() - run_start
    log_path = write_run_log(result)
    print(f"[OK] total {result.total_seconds:.1f}s -> log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
