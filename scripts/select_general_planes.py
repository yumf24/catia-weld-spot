from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Select generic planar weld faces from a registered primary STEP input.")
    parser.add_argument("part_id")
    parser.add_argument("--run-label", default="generic-selection")
    parser.parse_args()
    raise SystemExit("select_general_planes runtime is implemented in G05")


if __name__ == "__main__":
    main()
