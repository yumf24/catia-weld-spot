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

`component-simplify` is a regression dataset. The 2026-07-23 run
`data/component-simplify/20260723-105708-recall-optimization/` evaluated to
TP/FP/FN 30/6/10 with precision 83.33% and recall 75.00%. The current controlled
optimization gate is precision >90% and recall >90%, so this baseline does not
pass it. Its 10 false negatives comprise four plane-gap, four projected-AABB, and
two same-part-policy cases; neither same-part recovery nor an AABB fallback is a
production recovery path. This remains useful single-dataset regression evidence,
not a cross-part claim: no independent validation part is currently available.

## Gate

The workflow may report preliminary cross-part capability only after at least
two validation parts that were not used for threshold setting independently meet
the acceptance targets in `docs/ALG_updatev2.json`: per-dataset precision at
least 0.90 and recall at least 0.95, with reference mapping coverage at least
0.95 and geometric tolerances respected.
