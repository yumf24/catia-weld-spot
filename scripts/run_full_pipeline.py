"""Managed end-to-end pipeline: active CATIA document -> one run directory.

Run on Windows with CATIA V5 running and the registered source document open:

    python scripts/run_full_pipeline.py component --run-label full [--write] [--save-native]

All generated artifacts are written to ``data/<part-id>/<run-id>/``.  The
directory's ``manifest.json`` records the registered raw inputs, exact
parameters, and every artifact, so it is safe to keep multiple runs side by
side.  ``--write`` is opt-in; ``--save-native`` additionally saves CATIA's
native result under the same run directory and requires ``--write``.
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
from weld_core.data_layout import (  # noqa: E402
    DataLayoutError,
    create_run,
    register_artifact,
    update_run_manifest,
)
from weld_core.pipeline import run as run_pipeline  # noqa: E402
from weld_core.schema import dump_document  # noqa: E402


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
    run_dir: str = ""
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
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", stem) or "document"


def _default_label(part_number: str | None, limit: int | None) -> str:
    if part_number:
        label = f"part-{_safe_name(part_number).lower()}"
    else:
        label = "full"
    return f"{label}-limit-{limit}" if limit is not None else label


def write_run_log(result: RunResult, run_dir: Path) -> Path:
    path = run_dir / "run.log"
    t = result.times
    lines = [
        "Weld-pipeline full run (extract -> export -> enrich -> core -> write)",
        "=" * 48,
        f"{'timestamp':<22}: {datetime.now().isoformat(timespec='seconds')}",
        f"{'document':<22}: {result.document}",
        f"{'run directory':<22}: {result.run_dir}",
        "",
        "Timing",
        "-" * 48,
        f"{'extract (COM)':<22}: {t.extract_seconds:.3f} s",
        f"{'export STEP (COM)':<22}: {t.export_seconds:.3f} s",
        f"{'enrich (OCP)':<22}: {t.enrich_seconds:.3f} s",
        f"{'core (pure python)':<22}: {t.core_seconds:.3f} s",
        f"{'write (COM)':<22}: {t.write_seconds:.3f} s" if result.write_created is not None
        else f"{'write (COM)':<22}: skipped (--write not passed)",
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
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _save_native_document(document, run_dir: Path, part_id: str) -> Path:
    native_dir = run_dir / "native"
    native_dir.mkdir()
    suffix = Path(document.name).suffix or ".CATProduct"
    target = native_dir / f"{part_id}_with_weld_candidates{suffix}"
    try:
        document.save_as(str(target))
    except AttributeError:
        document.com_object.SaveAs(str(target))
    return target


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part_id", help="registered raw-data id, e.g. component")
    parser.add_argument("--run-label", default=None, help="optional lowercase run label")
    parser.add_argument("--write", action="store_true", help="write candidates into the active CATIA document")
    parser.add_argument("--save-native", action="store_true", help="save native CATIA result under this run (requires --write)")
    parser.add_argument("--part-number", default=None, help="passthrough to extract_faces")
    parser.add_argument("--limit", type=int, default=None, help="passthrough to extract_faces")
    args = parser.parse_args(argv)
    if args.save_native and not args.write:
        parser.error("--save-native requires --write")

    app = catia()
    document = app.active_document
    label = args.run_label or _default_label(args.part_number, args.limit)
    params = WeldParams()
    try:
        run_dir, _ = create_run(
            args.part_id,
            label,
            active_document=document.name,
            parameters={
                "part_number": args.part_number,
                "limit": args.limit,
                "weld_params": params.as_dict(),
                "write": args.write,
                "save_native": args.save_native,
            },
        )
    except DataLayoutError as exc:
        parser.error(str(exc))

    step_path = run_dir / "component.stp"
    faces_path = run_dir / "faces.json"
    enriched_path = run_dir / "faces.enriched.json"
    candidates_path = run_dir / "candidates.json"
    run_start = time.perf_counter()
    times = StageTimes()

    try:
        print("[1/5] extracting faces from active document (COM)...")
        faces_doc, extract_stats = ef.extract_faces(app, args.part_number, args.limit)
        dump_document(faces_doc, faces_path)
        register_artifact(run_dir, "faces", faces_path)
        times.extract_seconds = extract_stats.total_seconds
        print(f"      {extract_stats.faces_processed} faces ({extract_stats.planar_count} planar)")

        print("[2/5] exporting active document to STEP (COM)...")
        export_stats = es.export_step(app, step_path)
        register_artifact(run_dir, "step", step_path)
        times.export_seconds = export_stats.export_seconds
        print(f"      -> {step_path} ({export_stats.export_seconds:.1f}s)")

        print("[3/5] enriching faces with STEP-derived vertices (offline)...")
        faces_doc, enrich_stats = enrich_faces_document(faces_doc, str(step_path))
        dump_document(faces_doc, enriched_path)
        register_artifact(run_dir, "faces_enriched", enriched_path)
        times.enrich_seconds = enrich_stats.total_seconds
        totals = enrich_stats.totals
        print(f"      {totals.matched}/{totals.planar_com_faces} planar faces matched")

        print("[4/5] running weld_core pipeline (offline)...")
        core_start = time.perf_counter()
        candidates_doc = run_pipeline(faces_doc, params)
        times.core_seconds = time.perf_counter() - core_start
        dump_document(candidates_doc, candidates_path)
        register_artifact(run_dir, "candidates", candidates_path)
        print(f"      {len(candidates_doc.candidates)} candidates -> {candidates_path}")

        result = RunResult(
            document=document.name,
            run_dir=str(run_dir.relative_to(REPO_ROOT)),
            faces_total=extract_stats.faces_processed,
            faces_planar=extract_stats.planar_count,
            faces_matched=totals.matched,
            candidates=len(candidates_doc.candidates),
            times=times,
        )
        if args.write:
            print("[5/5] writing candidates back into the active document (COM)...")
            write_start = time.perf_counter()
            root_product = document.product
            part = wc.get_or_create_weld_part(app, root_product)
            body = wc.get_or_create_body(part)
            created, updated, staled = wc.write_candidates(part, body, candidates_doc.candidates)
            times.write_seconds = time.perf_counter() - write_start
            result.write_created, result.write_updated, result.write_staled = created, updated, staled
            if args.save_native:
                native_path = _save_native_document(document, run_dir, args.part_id)
                native_files = [
                    str(path.relative_to(run_dir))
                    for path in sorted(native_path.parent.rglob("*"))
                    if path.is_file()
                ]
                register_artifact(run_dir, "native", native_path, kind="catia-native", files=native_files)
            print(f"      {created} created, {updated} updated, {staled} newly marked stale")
        else:
            print("[5/5] skipped (pass --write to write candidates back into CATIA)")

        result.total_seconds = time.perf_counter() - run_start
        log_path = write_run_log(result, run_dir)
        register_artifact(run_dir, "run_log", log_path)
        update_run_manifest(run_dir, status="completed", completed_at=datetime.now().astimezone().isoformat(timespec="seconds"))
        print(f"[OK] total {result.total_seconds:.1f}s -> {run_dir}")
        return 0
    except Exception as exc:
        update_run_manifest(run_dir, status="failed", error=str(exc), failed_at=datetime.now().astimezone().isoformat(timespec="seconds"))
        raise


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
