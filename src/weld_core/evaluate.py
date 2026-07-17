"""Evaluate candidate weld points against real (ground-truth) weld points.

Pure Python/numpy, no pycatia/pywin32 — matches ``weld_core``'s independence
requirement. Ground truth is produced offline by
``scripts/extract_ground_truth.py`` (from ``data/SPOT.step``'s weld-spot
marker balls) into a ``ground_truth.json`` (see ``weld_core.schema.
GroundTruthDocument``); candidates come from the normal pipeline's
``candidates.json``.

Matching is a greedy nearest-distance one-to-one assignment: consider every
(ground-truth, candidate) pair within ``tolerance_mm`` of each other, sorted
by distance ascending, and take each pair in order as long as both its
points are still unclaimed. This is the standard approximation used for
point-set detection evaluation (e.g. COCO-style keypoint matching) — it is
not the exact optimal (min-cost) assignment, but for this problem's scale
(low hundreds of points, real weld points spaced >=20mm apart while the
sensible tolerance is a few mm) the two never disagree in practice, and it
avoids pulling in ``scipy`` for a full linear-sum-assignment solver.

V1 priority (see PLAN.md: "尽量不漏检") means **recall** (did we find every
real weld point?) is the metric that matters most; precision (how many
candidates were spurious) is expected to be lower and is not itself a
failure — extra candidates get human review, missed ones do not.

Usage:
    python -m weld_core.evaluate <ground_truth.json> <candidates.json> [evaluation.json] [--tolerance MM]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from .schema import (
    CandidatesDocument,
    EvalMatch,
    EvaluationDocument,
    EvaluationMeta,
    EvalSummary,
    GroundTruthDocument,
    dump_document,
    load_candidates,
    load_ground_truth,
)

# Sensible default: bigger than the marker ball radius (3mm) and the
# expected placement error of the region-midpoint layout, far smaller than
# the pipeline's 20mm minimum point spacing so it can't cross-match distinct
# weld points. Callers with a different accuracy bar should override this.
DEFAULT_TOLERANCE_MM = 10.0


def evaluate(
    ground_truth: GroundTruthDocument,
    candidates: CandidatesDocument,
    tolerance_mm: float = DEFAULT_TOLERANCE_MM,
    ground_truth_source: str = "",
    candidates_source: str = "",
) -> EvaluationDocument:
    gt_points = ground_truth.points
    cand_points = candidates.candidates

    pairs: list[tuple[float, int, int]] = []
    if gt_points and cand_points:
        gt_pos = np.array([p.position for p in gt_points], dtype=float)
        cand_pos = np.array([c.position for c in cand_points], dtype=float)
        dist = np.linalg.norm(gt_pos[:, None, :] - cand_pos[None, :, :], axis=2)
        gi, ci = np.where(dist <= tolerance_mm)
        pairs = [(float(dist[i, j]), int(i), int(j)) for i, j in zip(gi, ci)]
    pairs.sort(key=lambda p: p[0])

    matched_gt: set[int] = set()
    matched_cand: set[int] = set()
    matches: list[EvalMatch] = []
    for d, i, j in pairs:
        if i in matched_gt or j in matched_cand:
            continue
        matched_gt.add(i)
        matched_cand.add(j)
        matches.append(
            EvalMatch(
                ground_truth_id=gt_points[i].id,
                candidate_id=cand_points[j].id,
                distance_mm=d,
            )
        )

    unmatched_gt = [p.id for idx, p in enumerate(gt_points) if idx not in matched_gt]
    unmatched_cand = [c.id for idx, c in enumerate(cand_points) if idx not in matched_cand]

    tp = len(matches)
    fn = len(unmatched_gt)
    fp = len(unmatched_cand)
    distances = [m.distance_mm for m in matches]

    summary = EvalSummary(
        num_ground_truth=len(gt_points),
        num_candidates=len(cand_points),
        true_positives=tp,
        false_negatives=fn,
        false_positives=fp,
        recall=(tp / (tp + fn)) if (tp + fn) else 1.0,
        precision=(tp / (tp + fp)) if (tp + fp) else 1.0,
        mean_error_mm=float(np.mean(distances)) if distances else 0.0,
        max_error_mm=float(np.max(distances)) if distances else 0.0,
    )

    return EvaluationDocument(
        meta=EvaluationMeta(
            ground_truth_source=ground_truth_source,
            candidates_source=candidates_source,
            tolerance_mm=tolerance_mm,
        ),
        summary=summary,
        matches=matches,
        unmatched_ground_truth=unmatched_gt,
        unmatched_candidates=unmatched_cand,
    )


def _print_report(doc: EvaluationDocument, ground_truth: GroundTruthDocument) -> None:
    s = doc.summary
    print(f"tolerance: {doc.meta.tolerance_mm} mm")
    print(f"ground truth points: {s.num_ground_truth}   candidates: {s.num_candidates}")
    print(f"matched (TP): {s.true_positives}   missed (FN): {s.false_negatives}   extra (FP): {s.false_positives}")
    print(f"recall: {s.recall:.1%}   precision: {s.precision:.1%}")
    if s.true_positives:
        print(f"match error: mean {s.mean_error_mm:.3f} mm, max {s.max_error_mm:.3f} mm")
    if doc.unmatched_ground_truth:
        by_id = {p.id: p for p in ground_truth.points}
        print("\nmissed ground-truth points (no candidate within tolerance):")
        for gid in doc.unmatched_ground_truth:
            p = by_id[gid]
            print(f"  {gid}: {p.position}  label={p.label!r}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ground_truth", type=Path)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("out", type=Path, nargs="?", default=None)
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE_MM, help="match tolerance in mm")
    args = parser.parse_args(argv)

    out_path = args.out or args.ground_truth.with_name("evaluation.json")

    ground_truth = load_ground_truth(args.ground_truth)
    candidates = load_candidates(args.candidates)
    doc = evaluate(
        ground_truth,
        candidates,
        tolerance_mm=args.tolerance,
        ground_truth_source=str(args.ground_truth),
        candidates_source=str(args.candidates),
    )
    dump_document(doc, out_path)
    _print_report(doc, ground_truth)
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
