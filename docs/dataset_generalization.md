# Dataset Boundary and Generalization Gate

This project separates registered CAD inputs by dataset so runtime behavior
cannot depend on one sample's identity.

## Dataset Roles

- Parameter development set: parts used to choose generic thresholds and inspect
  failure modes. Results may guide parameter changes, but sample ids, file names,
  face counts, face ids, labels, and input hashes must not enter production
  selection logic.
- Validation set: at least two independent parts not used while setting
  thresholds. Each part must have an explicit offline reference only for
  evaluation.
- Held-out test set: final parts kept aside until the workflow and thresholds are
  frozen for a release candidate.

## Current Regression

`component-simplify` is a regression dataset. The 2026-07-22 run
`data/component-simplify/20260722-163200-generic-regression/` selected 19 CAD
faces, produced 15 candidates, and evaluated to TP/FP/FN 17/2/23 with precision
89.47% and recall 42.50%. This is useful for diagnosing missed weld-adjacent
faces, but it is not a cross-part claim.

## Gate

The workflow may report preliminary cross-part capability only after at least
two validation parts that were not used for threshold setting independently meet
the acceptance targets in `docs/ALG_updatev2.json`: per-dataset precision at
least 0.90 and recall at least 0.95, with reference mapping coverage at least
0.95 and geometric tolerances respected.
