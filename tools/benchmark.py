"""Runs every solver on every stage and writes the experiment table used by the report.

    python tools/benchmark.py                       # all stages -> docs/experiments/results.csv
    python tools/benchmark.py --groups hard split   # only some levels/ sub-folders
    python tools/benchmark.py --repeat 5 --out other.csv

Each row is one (stage, solver) pair with the four required metrics: search time (median of
`--repeat` runs, in milliseconds), peak memory (tracemalloc, KiB), expanded nodes and solution
length, plus the path cost. Searches slower than `--slow` seconds run only once. The geometric
A* row is skipped on split stages, where that bound is not admissible.
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.level_loader import load_level  # noqa: E402
from solvers import astar, bfs, dfs, ucs  # noqa: E402

GROUPS = ("basic", "advanced", "split", "hard", "demo")
SOLVERS = {
    "BFS": bfs.solve,
    "DFS": dfs.solve_dfs,
    "IDS": dfs.solve_ids,
    "UCS": ucs.solve,
    "A* h=0": lambda level: astar.solve(level, heuristic=astar.zero_heuristic),
    "A* geometric": lambda level: astar.solve(level, heuristic=astar.astar_heuristic),
    "A* relaxed": lambda level: astar.solve(level, heuristic=astar.relaxed_heuristic),
}
FIELDS = ("group", "stage", "solver", "found", "solution_length", "path_cost",
          "expanded_nodes", "peak_memory_kib", "search_time_ms")


def measure(solver, level, repeat: int, slow: float) -> dict:
    runs = [solver(level)]
    while len(runs) < repeat and runs[0].search_time < slow:
        runs.append(solver(level))
    result = runs[0]
    return {
        "found": result.found,
        "solution_length": result.solution_length if result.found else "",
        "path_cost": result.path_cost if result.found else "",
        "expanded_nodes": result.expanded_nodes,
        "peak_memory_kib": round(result.peak_memory / 1024, 1),
        "search_time_ms": round(statistics.median(r.search_time for r in runs) * 1000, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--groups", nargs="+", default=GROUPS, choices=GROUPS)
    parser.add_argument("--repeat", type=int, default=3, help="runs per search (median time)")
    parser.add_argument("--slow", type=float, default=2.0, help="seconds after which a search runs once")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "experiments" / "results.csv")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for group in args.groups:
            for path in sorted((ROOT / "levels" / group).glob("*.json")):
                level = load_level(path)
                for name, solver in SOLVERS.items():
                    if name == "A* geometric" and level.split_switches:
                        continue
                    row = {"group": group, "stage": path.stem, "solver": name,
                           **measure(solver, level, args.repeat, args.slow)}
                    writer.writerow(row)
                    handle.flush()
                    print(f"{group}/{path.stem:28s} {name:13s} len={row['solution_length']!s:>4} "
                          f"expanded={row['expanded_nodes']:>7} time={row['search_time_ms']:>10} ms",
                          flush=True)
    print(f"wrote {args.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
