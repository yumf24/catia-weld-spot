"""Merge STEP-derived vertices into a COM-extracted faces.json.

Fills the ``vertices`` gap documented in DEVLOG.md: ``catia/extract_faces.py``
(CATIA COM) cannot reliably enumerate per-face vertices, so every face comes
out with ``vertices=[]`` and ``manual_review=True``. This script parses a
STEP export of the same document via ``weld_core.step_geometry`` (offline,
no CATIA/pycatia involved) and, per CATIA PartNumber, matches each planar COM
face to its STEP counterpart by geometry (centroid distance + normal angle +
area), then fills in ``vertices`` and clears ``manual_review`` for confident
matches.

Run (no CATIA needed, just the two JSON/STEP files):

    python scripts/enrich_faces_with_step.py <faces.json> <component.step> <output.json>
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from weld_core import step_geometry as sg  # noqa: E402
from weld_core.geometry import normal_angle_deg  # noqa: E402
from weld_core.schema import FacesDocument, dump_document, load_faces  # noqa: E402

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

MAX_CENTROID_DIST_MM = 1.0
MAX_NORMAL_ANGLE_DEG = 2.0
MAX_AREA_REL_DIFF = 0.05


@dataclass
class PartStats:
    planar_com_faces: int = 0
    matched: int = 0
    mismatched_planarity: int = 0
    unmatched: int = 0
    part_missing_in_step: int = 0


@dataclass
class RunStats:
    faces_path: str = ""
    step_path: str = ""
    output_path: str = ""
    parse_seconds: float = 0.0
    match_seconds: float = 0.0
    total_seconds: float = 0.0
    per_part: dict[str, PartStats] = field(default_factory=dict)

    @property
    def totals(self) -> PartStats:
        out = PartStats()
        for s in self.per_part.values():
            out.planar_com_faces += s.planar_com_faces
            out.matched += s.matched
            out.mismatched_planarity += s.mismatched_planarity
            out.unmatched += s.unmatched
            out.part_missing_in_step += s.part_missing_in_step
        return out


def _safe_name(name: str) -> str:
    stem = Path(name).stem or name
    import re

    return re.sub(r"[^A-Za-z0-9_.-]+", "_", stem) or "doc"


def write_run_log(stats: RunStats) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"enrich_faces_with_step_{_safe_name(stats.faces_path)}_{stamp}.log"

    t = stats.totals
    lines = [
        "Weld-pipeline STEP vertex enrichment — run log",
        "=" * 48,
        f"{'timestamp':<22}: {datetime.now().isoformat(timespec='seconds')}",
        f"{'faces.json':<22}: {stats.faces_path}",
        f"{'step file':<22}: {stats.step_path}",
        f"{'output':<22}: {stats.output_path}",
        "",
        "Timing",
        "-" * 48,
        f"{'STEP parse':<22}: {stats.parse_seconds:.3f} s",
        f"{'matching':<22}: {stats.match_seconds:.3f} s",
        f"{'total':<22}: {stats.total_seconds:.3f} s",
        "",
        "Totals (across all parts)",
        "-" * 48,
        f"{'planar COM faces':<25}: {t.planar_com_faces}",
        f"{'  matched':<25}: {t.matched}",
        f"{'  mismatched planarity':<25}: {t.mismatched_planarity}",
        f"{'  unmatched (no candidate)':<25}: {t.unmatched}",
        f"{'  part missing in STEP':<25}: {t.part_missing_in_step}",
        "",
        "Per part",
        "-" * 48,
    ]
    for part, s in sorted(stats.per_part.items()):
        lines.append(
            f"{part:<30} planar={s.planar_com_faces:<6} matched={s.matched:<6} "
            f"mismatched={s.mismatched_planarity:<4} unmatched={s.unmatched:<4} "
            f"missing_in_step={s.part_missing_in_step}"
        )
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log_path


def _match_cost(com_face, step_face) -> float | None:
    """Combined match cost, or None if any threshold is exceeded."""
    centroid_dist = float(np.linalg.norm(np.asarray(com_face.centroid) - np.asarray(step_face.centroid)))
    if centroid_dist > MAX_CENTROID_DIST_MM:
        return None

    angle = normal_angle_deg(com_face.normal, step_face.normal)
    if angle > MAX_NORMAL_ANGLE_DEG:
        return None

    area_a, area_b = com_face.area, step_face.area
    denom = max(area_a, area_b, 1e-9)
    area_rel_diff = abs(area_a - area_b) / denom
    if area_rel_diff > MAX_AREA_REL_DIFF:
        return None

    return centroid_dist + angle * 0.1 + area_rel_diff * 10.0


def _match_part_group(com_faces, step_faces) -> dict[str, object]:
    """Greedy one-to-one matching within a single part's faces.

    Returns a dict keyed by COM face id -> matched StepFace (or absent if
    no candidate cleared the thresholds).
    """
    candidates = []
    for ci, cf in enumerate(com_faces):
        for si, sf in enumerate(step_faces):
            cost = _match_cost(cf, sf)
            if cost is not None:
                candidates.append((cost, ci, si))
    candidates.sort(key=lambda c: c[0])

    used_com: set[int] = set()
    used_step: set[int] = set()
    result: dict[str, object] = {}
    for _cost, ci, si in candidates:
        if ci in used_com or si in used_step:
            continue
        used_com.add(ci)
        used_step.add(si)
        result[com_faces[ci].id] = step_faces[si]
    return result


def enrich_faces_document(doc: FacesDocument, step_path: str) -> tuple[FacesDocument, RunStats]:
    stats = RunStats(step_path=step_path)
    run_start = time.perf_counter()

    parse_start = time.perf_counter()
    step_groups = sg.parse_step_faces(step_path)
    stats.parse_seconds = time.perf_counter() - parse_start

    by_part: dict[str, list] = {}
    for f in doc.faces:
        by_part.setdefault(f.part, []).append(f)

    match_start = time.perf_counter()
    for part_name, com_faces in by_part.items():
        planar_faces = [f for f in com_faces if f.surface_type == "planar"]
        part_stats = PartStats(planar_com_faces=len(planar_faces))
        stats.per_part[part_name] = part_stats

        step_faces = step_groups.get(part_name)
        if step_faces is None:
            part_stats.part_missing_in_step = len(planar_faces)
            for f in planar_faces:
                f.reason = "part not found in STEP export"
            continue

        matches = _match_part_group(planar_faces, step_faces)
        for f in planar_faces:
            matched = matches.get(f.id)
            if matched is None:
                part_stats.unmatched += 1
                f.manual_review = True
                f.reason = "no matching STEP face found within threshold"
                continue
            if not matched.is_planar:
                part_stats.mismatched_planarity += 1
                f.manual_review = True
                f.reason = (
                    f"STEP-derived geometry indicates non-planar face "
                    f"(residual={matched.max_residual:.4f}mm) despite COM planar classification"
                )
                continue
            part_stats.matched += 1
            f.vertices = matched.vertices
            f.manual_review = False
            f.reason = ""

    stats.match_seconds = time.perf_counter() - match_start
    stats.total_seconds = time.perf_counter() - run_start
    return doc, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("faces_json", type=Path, help="COM-extracted faces.json to enrich")
    parser.add_argument("step_file", type=Path, help="STEP export of the same document")
    parser.add_argument("output", type=Path, help="path to write the enriched faces.json")
    args = parser.parse_args()

    doc = load_faces(args.faces_json)
    doc, stats = enrich_faces_document(doc, str(args.step_file))
    stats.faces_path = str(args.faces_json)
    stats.output_path = str(args.output)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    dump_document(doc, args.output)
    log_path = write_run_log(stats)

    t = stats.totals
    print(
        f"[OK] {t.matched}/{t.planar_com_faces} planar faces matched "
        f"({t.mismatched_planarity} mismatched, {t.unmatched} unmatched, "
        f"{t.part_missing_in_step} part-missing) -> {args.output}"
    )
    print(f"[PERF] parse {stats.parse_seconds:.1f}s, match {stats.match_seconds:.1f}s -> log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
