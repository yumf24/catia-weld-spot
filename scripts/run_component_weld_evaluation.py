"""Create an isolated, truth-free component weld candidate run.

Only the raw manifest's ``primary_model`` is read.  Real weld markers are
evaluation-only and must be handled by a later explicit evaluation step.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from weld_core.component_weld_evaluation import create_component_candidate_run  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", "--run-label", dest="run_label", default="candidate", help="managed run label")
    args = parser.parse_args(argv)
    try:
        run_dir = create_component_candidate_run(args.run_label)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] isolated component candidate run -> {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
