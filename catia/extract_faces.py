"""Phase 1 extractor: CATIA V5 (pycatia) -> faces.json.

Run on Windows with CATIA V5 running and the target Part or Product document
active (`Documents.Item(...).Activate()` or opened/focused in the UI):

    python catia/extract_faces.py output/faces.json [--part-number NAME] [--limit N]

Notes from real-machine validation (see DEVLOG.md):
- Face geometry (area/plane/centroid) is read via
  ``SPAWorkbench.GetMeasurableInContext(face_ref, leaf_product)`` at the
  Product level, or ``GetMeasurable`` directly when a single Part document is
  active. ``GetPlane`` raises for non-planar faces -> surface_type set
  accordingly.
- Per-face vertex enumeration (``Selection.Search`` scoped to a single face
  via ``,sel``/``,(sel)``) is NOT reliable in this CATIA/pycatia setup: it
  either returns 0 or silently widens to an uncontrolled, much larger scope.
  So ``vertices`` is always left empty here and ``manual_review`` is set,
  matching the contract's documented fallback ("顶点缺失 -> 标 manual_review").
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from pycatia import catia

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from weld_core.schema import FaceRecord, FacesDocument, FacesMeta, dump_document  # noqa: E402

M2_TO_MM2 = 1_000_000.0
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


@dataclass
class RunStats:
    """Timing/throughput counters for one extract_faces run (perf log, not faces.json)."""

    document: str = ""
    context: str = ""
    part_number_filter: str | None = None
    limit: int | None = None
    faces_found_total: int = 0
    faces_skipped_by_filter: int = 0
    faces_processed: int = 0
    planar_count: int = 0
    non_planar_count: int = 0
    read_errors: int = 0
    search_seconds: float = 0.0
    extract_seconds: float = 0.0
    total_seconds: float = 0.0
    output_path: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def faces_per_second(self) -> float:
        return self.faces_processed / self.extract_seconds if self.extract_seconds > 0 else 0.0


def _safe_name(name: str) -> str:
    stem = Path(name).stem or name
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", stem) or "doc"


def write_run_log(stats: RunStats) -> Path:
    """Persist a human-readable perf log, named after scope + run timestamp."""

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    scope = _safe_name(stats.part_number_filter) if stats.part_number_filter else "ALL"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"extract_faces_{_safe_name(stats.document)}_{scope}_{stamp}.log"

    lines = [
        "Weld-pipeline face extraction — performance log",
        "=" * 48,
        f"{'timestamp':<22}: {datetime.now().isoformat(timespec='seconds')}",
        f"{'document':<22}: {stats.document}",
        f"{'context':<22}: {stats.context}",
        f"{'part_number filter':<22}: {stats.part_number_filter or '(none — full document)'}",
        f"{'face limit':<22}: {stats.limit if stats.limit is not None else '(none)'}",
        "",
        "Timing",
        "-" * 48,
        f"{'face search':<22}: {stats.search_seconds:.3f} s",
        f"{'per-face extraction':<22}: {stats.extract_seconds:.3f} s "
        f"({stats.faces_processed} faces)",
        f"{'total':<22}: {stats.total_seconds:.3f} s",
        f"{'throughput':<22}: {stats.faces_per_second:.1f} faces/sec",
        "",
        "Volume",
        "-" * 48,
        f"{'faces found (pre-filter)':<25}: {stats.faces_found_total}",
        f"{'faces skipped by filter':<25}: {stats.faces_skipped_by_filter}",
        f"{'faces processed':<25}: {stats.faces_processed}",
        f"{'  planar':<25}: {stats.planar_count}",
        f"{'  non_planar':<25}: {stats.non_planar_count}",
        f"{'read errors (area/cog)':<25}: {stats.read_errors}",
        "",
        "Output",
        "-" * 48,
        f"faces.json  : {stats.output_path}",
        f"warnings    : {len(stats.warnings)}",
    ]
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log_path


def normal_from_plane(plane) -> tuple[float, float, float]:
    _ox, _oy, _oz, d1x, d1y, d1z, d2x, d2y, d2z = plane
    d1 = np.array([d1x, d1y, d1z])
    d2 = np.array([d2x, d2y, d2z])
    n = np.cross(d1, d2)
    norm = np.linalg.norm(n)
    if norm < 1e-12:
        return (0.0, 0.0, 1.0)
    n = n / norm
    return (float(n[0]), float(n[1]), float(n[2]))


def part_number_of(leaf_product) -> str:
    try:
        pn = leaf_product.com_object.PartNumber
        if pn:
            return str(pn)
    except Exception:
        pass
    try:
        nm = leaf_product.name
        if nm:
            return str(nm)
    except Exception:
        pass
    return "UNKNOWN"


def extract_faces(
    app, part_number_filter: str | None, limit: int | None
) -> tuple[FacesDocument, RunStats]:
    run_start = time.perf_counter()
    ad = app.active_document
    is_product = type(ad).__name__ == "ProductDocument"
    context = "product" if is_product else "part"
    spa = ad.spa_workbench()
    sel = ad.selection
    sel.clear()

    search_start = time.perf_counter()
    sel.search("Topology.CGMFace,all")
    search_seconds = time.perf_counter() - search_start
    n_faces = sel.count2

    warnings: list[str] = [
        "vertices not extracted (unreliable Selection.Search face-scoping in this "
        "CATIA/pycatia setup); manual_review set on every face as a result",
        "body name not resolved per face (no reliable per-face Body lookup at "
        "product scope); 'body' is a constant placeholder, not a real Body id",
    ]
    faces: list[FaceRecord] = []
    face_counter: dict[str, int] = {}
    skipped_by_filter = 0
    read_errors = 0

    extract_start = time.perf_counter()
    for i in range(1, n_faces + 1):
        if limit is not None and len(faces) >= limit:
            break

        el = sel.item(i)
        ref = el.reference

        if is_product:
            leaf = el.leaf_product
            part_name = part_number_of(leaf)
            if part_number_filter and part_name != part_number_filter:
                skipped_by_filter += 1
                continue
            measurable = spa.get_measurable_in_context(ref, leaf)
        else:
            part_name = ad.name
            measurable = spa.get_measurable(ref)

        local_idx = face_counter.get(part_name, 0) + 1
        face_counter[part_name] = local_idx
        body_name = "unknown"
        face_id = f"{part_name}/face_{local_idx}"

        try:
            area_mm2 = float(measurable.area) * M2_TO_MM2
        except Exception as exc:
            warnings.append(f"{face_id}: area read failed ({exc})")
            read_errors += 1
            area_mm2 = 0.0

        try:
            plane = measurable.get_plane()
            surface_type = "planar"
            plane_origin = (float(plane[0]), float(plane[1]), float(plane[2]))
            normal = normal_from_plane(plane)
        except Exception:
            surface_type = "non_planar"
            plane_origin = (0.0, 0.0, 0.0)
            normal = (0.0, 0.0, 1.0)

        try:
            cog = measurable.get_cog()
            centroid = (float(cog[0]), float(cog[1]), float(cog[2]))
        except Exception as exc:
            warnings.append(f"{face_id}: centroid read failed ({exc})")
            read_errors += 1
            centroid = plane_origin

        reason_parts = []
        if surface_type == "non_planar":
            reason_parts.append("non-planar surface (V1 skips)")
        reason_parts.append("vertices unavailable -> cannot compute projected AABB")

        faces.append(
            FaceRecord(
                id=face_id,
                part=part_name,
                body=body_name,
                surface_type=surface_type,
                area=area_mm2,
                normal=normal,
                plane_origin=plane_origin,
                centroid=centroid,
                vertices=[],
                manual_review=True,
                reason="; ".join(reason_parts),
            )
        )

    extract_seconds = time.perf_counter() - extract_start
    planar_count = sum(1 for f in faces if f.surface_type == "planar")

    stats = RunStats(
        document=ad.name,
        context=context,
        part_number_filter=part_number_filter,
        limit=limit,
        faces_found_total=n_faces,
        faces_skipped_by_filter=skipped_by_filter,
        faces_processed=len(faces),
        planar_count=planar_count,
        non_planar_count=len(faces) - planar_count,
        read_errors=read_errors,
        search_seconds=search_seconds,
        extract_seconds=extract_seconds,
        total_seconds=time.perf_counter() - run_start,
        warnings=warnings,
    )

    doc = FacesDocument(
        meta=FacesMeta(part=ad.name, context=context, warnings=warnings),
        faces=faces,
    )
    return doc, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="path to write faces.json")
    parser.add_argument(
        "--part-number",
        default=None,
        help="only extract faces belonging to this PartNumber (product context only)",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="stop after this many faces (for quick tests)"
    )
    args = parser.parse_args()

    app = catia()
    doc, stats = extract_faces(app, args.part_number, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    dump_document(doc, args.output)
    stats.output_path = str(args.output)
    log_path = write_run_log(stats)

    print(
        f"[OK] wrote {stats.faces_processed} faces ({stats.planar_count} planar) -> {args.output}"
    )
    print(
        f"[PERF] {stats.total_seconds:.3f}s total, {stats.faces_per_second:.1f} faces/sec "
        f"-> log: {log_path}"
    )
    for w in doc.meta.warnings:
        print(f"[WARN] {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
