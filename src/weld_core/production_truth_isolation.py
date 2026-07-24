"""Guards that keep evaluation evidence out of production readers.

The guard is intentionally small and dependency-free so it can be used by
the pure-Python core as well as CATIA entry points.  It protects filenames,
not a whole run directory: a candidate run may later contain evaluation
artifacts, but production code must never open those artifacts.
"""

from __future__ import annotations

from pathlib import Path


class ProductionTruthIsolationError(ValueError):
    """Raised when a production reader is given an evaluation-only input."""


_FORBIDDEN_FILENAME_TOKENS = (
    "spot",
    "ground_truth",
    "truth_adjudication",
    "adjudication",
    "frontier",
    "operating_frontier",
    "candidate_chain_atlas",
    "error_analysis",
)


def assert_production_read_path(path: str | Path) -> Path:
    """Return *path* unless its filename denotes evaluation-only evidence.

    The caller must invoke this immediately before opening a production input.
    Checking only ``Path.name`` deliberately permits normal production files
    stored in a run directory which happens to also contain offline reports.
    """
    resolved = Path(path)
    filename = resolved.name.casefold()
    forbidden = next((token for token in _FORBIDDEN_FILENAME_TOKENS if token in filename), None)
    if forbidden is not None:
        raise ProductionTruthIsolationError(
            f"production input {resolved} is evaluation-only (matched {forbidden!r})"
        )
    return resolved
