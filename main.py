"""Bloxorz Solver - CSC14003 Project 1.

Usage:
    python main.py                                         # open the GUI on the first stage
    python main.py levels/advanced/07_advanced_mix.json    # open a specific stage
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Bloxorz game with BFS, DFS, IDS, UCS and A* solvers.")
    parser.add_argument("stage", nargs="?", type=Path,
                        help="stage file to open first (default: first stage in levels/)")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT))  # lets `engine`, `solvers`, `gui` import from any working dir
    from gui.app import run

    stage = args.stage.resolve() if args.stage else None
    if stage is not None and not stage.is_file():
        parser.error(f"stage file not found: {args.stage}")
    run(ROOT / "levels", stage)


if __name__ == "__main__":
    main()
