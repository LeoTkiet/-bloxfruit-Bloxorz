"""Depth-first search and iterative-deepening search for Bloxorz.

Both strategies are written from scratch and call only the shared engine
(``get_successors`` / ``is_goal``). Every visited structure is keyed by the
complete immutable ``GameState`` (position, orientation or split cubes, active
cube, *and* bridge mask), so two placements that differ only in their bridge
configuration are never merged.

DFS (``strategy="dfs"``)
    Classic graph-search DFS with an explicit stack of successor iterators, so
    it never hits Python's recursion limit. A global ``visited`` set stops
    cycles and re-exploration. It is complete on the finite state space but
    does *not* return shortest solutions.

IDS (``strategy="ids"``)
    Iterative deepening: repeated depth-limited DFS with limit 0, 1, 2, ...
    Within one iteration a ``best_depth`` map re-opens a state only when it is
    reached at a strictly smaller depth, which prevents cycles while keeping
    the search sound and complete for each limit. With unit step costs the
    first solution found is a shortest one, like BFS, using only
    ``O(depth)`` stack memory plus the per-iteration depth map. It stops with
    "not found" as soon as an iteration never touches its depth limit, i.e.
    the whole reachable graph has been exhausted, so unsolvable levels
    terminate.

Metric conventions (same as BFS)
    * ``expanded_nodes``: non-goal states whose successors are generated. For
      IDS this is summed over all iterations (states are re-expanded).
    * ``solution_length``: number of moves; ``path_cost``: sum of step costs.
    * ``search_time`` / ``peak_memory``: wall clock and extra traced bytes for
      the whole search including path reconstruction.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from time import perf_counter
import tracemalloc
from typing import Callable, Iterator

from engine.core import Action, GameState, Level, Successor, get_successors, is_goal
from engine.level_loader import load_level

from .common import SolverResult


STRATEGIES = ("dfs", "ids")


@dataclass(frozen=True, slots=True)
class _Outcome:
    """Raw result of one search run, before metrics are attached."""

    moves: tuple[Action, ...] | None
    states: tuple[GameState, ...]
    path_cost: float
    expanded_nodes: int



class _Path:
    """The current root-to-node path plus one successor iterator per open node.

    ``states`` always has one more element than ``actions``/``costs``; the
    iterator on top belongs to the last state. Because DFS keeps exactly the
    current path, the solution is simply the path when the goal is reached.
    """

    __slots__ = ("states", "actions", "costs", "iterators")

    def __init__(self, root: GameState) -> None:
        self.states: list[GameState] = [root]
        self.actions: list[Action] = []
        self.costs: list[float] = []
        self.iterators: list[Iterator[Successor]] = []

    @property
    def depth(self) -> int:
        """Number of moves from the root to the last state."""

        return len(self.actions)

    def push(self, action: Action, state: GameState, cost: float) -> None:
        self.actions.append(action)
        self.states.append(state)
        self.costs.append(cost)

    def pop(self) -> None:
        self.states.pop()
        if self.actions:
            self.actions.pop()
            self.costs.pop()

    def found(self, expanded_nodes: int) -> _Outcome:
        return _Outcome(
            moves=tuple(self.actions),
            states=tuple(self.states),
            path_cost=float(sum(self.costs)),
            expanded_nodes=expanded_nodes,
        )


def _trivial_outcome(start_state: GameState) -> _Outcome:
    return _Outcome(moves=(), states=(start_state,), path_cost=0.0, expanded_nodes=0)


def _dfs(level: Level, start_state: GameState) -> _Outcome:
    """Graph-search DFS with a global visited set over full states."""

    if is_goal(level, start_state):
        return _trivial_outcome(start_state)

    visited: set[GameState] = {start_state}
    path = _Path(start_state)
    path.iterators.append(iter(get_successors(level, start_state)))
    expanded_nodes = 1

    while path.iterators:
        descended = False
        for action, next_state, cost in path.iterators[-1]:
            if next_state in visited:
                continue
            visited.add(next_state)
            path.push(action, next_state, cost)
            if is_goal(level, next_state):
                return path.found(expanded_nodes)
            expanded_nodes += 1
            path.iterators.append(iter(get_successors(level, next_state)))
            descended = True
            break
        if not descended:
            path.iterators.pop()
            path.pop()

    return _Outcome(None, (), 0.0, expanded_nodes)


def _depth_limited(
    level: Level,
    start_state: GameState,
    limit: int,
) -> tuple[_Outcome | None, int, bool]:
    """One IDS iteration. Returns ``(solution, expanded_nodes, hit_limit)``.

    ``hit_limit`` is true when some non-goal state sat exactly at the depth
    limit, meaning a deeper iteration might still find more states.
    """

    if limit == 0:
        return None, 0, True

    best_depth: dict[GameState, int] = {start_state: 0}
    path = _Path(start_state)
    path.iterators.append(iter(get_successors(level, start_state)))
    expanded_nodes = 1
    hit_limit = False

    while path.iterators:
        child_depth = path.depth + 1
        descended = False
        for action, next_state, cost in path.iterators[-1]:
            if best_depth.get(next_state, child_depth + 1) <= child_depth:
                continue
            best_depth[next_state] = child_depth
            path.push(action, next_state, cost)
            if is_goal(level, next_state):
                return path.found(expanded_nodes), expanded_nodes, hit_limit
            if child_depth >= limit:
                hit_limit = True
                path.pop()
                continue
            expanded_nodes += 1
            path.iterators.append(iter(get_successors(level, next_state)))
            descended = True
            break
        if not descended:
            path.iterators.pop()
            path.pop()

    return None, expanded_nodes, hit_limit


def _ids(level: Level, start_state: GameState, max_depth: int | None) -> _Outcome:
    """Iterative deepening over depth limits 0, 1, 2, ..."""

    if is_goal(level, start_state):
        return _trivial_outcome(start_state)

    total_expanded = 0
    limit = 0
    while max_depth is None or limit <= max_depth:
        solution, expanded_nodes, hit_limit = _depth_limited(level, start_state, limit)
        total_expanded += expanded_nodes
        if solution is not None:
            return _Outcome(
                moves=solution.moves,
                states=solution.states,
                path_cost=solution.path_cost,
                expanded_nodes=total_expanded,
            )
        if not hit_limit:
            break  # the reachable graph is exhausted: no solution exists
        limit += 1

    return _Outcome(None, (), 0.0, total_expanded)


def _measure(search: Callable[[], _Outcome]) -> SolverResult:
    """Run ``search`` under the shared timer and peak-memory measurement."""

    started_tracing = not tracemalloc.is_tracing()
    if started_tracing:
        tracemalloc.start()
    tracemalloc.reset_peak()
    baseline_memory, _ = tracemalloc.get_traced_memory()
    start_time = perf_counter()

    try:
        outcome = search()
        search_time = perf_counter() - start_time
        _current, peak_memory = tracemalloc.get_traced_memory()
        measured_peak = max(0, peak_memory - baseline_memory)
    finally:
        if started_tracing:
            tracemalloc.stop()

    if outcome.moves is None:
        return SolverResult(
            found=False,
            moves=(),
            states=(),
            search_time=search_time,
            peak_memory=measured_peak,
            expanded_nodes=outcome.expanded_nodes,
            solution_length=0,
            path_cost=None,
        )
    return SolverResult(
        found=True,
        moves=outcome.moves,
        states=outcome.states,
        search_time=search_time,
        peak_memory=measured_peak,
        expanded_nodes=outcome.expanded_nodes,
        solution_length=len(outcome.moves),
        path_cost=outcome.path_cost,
    )


def solve_dfs(level: Level, initial_state: GameState | None = None) -> SolverResult:
    """Depth-first search; finds *a* solution, not necessarily a shortest one."""

    start_state = initial_state if initial_state is not None else level.initial_state
    return _measure(lambda: _dfs(level, start_state))


def solve_ids(
    level: Level,
    initial_state: GameState | None = None,
    *,
    max_depth: int | None = None,
) -> SolverResult:
    """Iterative deepening; shortest in *moves* (optimal for unit step costs).

    ``max_depth`` optionally caps the deepest iteration; without it the search
    runs until a solution exists or the reachable graph is exhausted.
    """

    if max_depth is not None and max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    start_state = initial_state if initial_state is not None else level.initial_state
    return _measure(lambda: _ids(level, start_state, max_depth))


def solve(
    level: Level,
    initial_state: GameState | None = None,
    *,
    strategy: str = "dfs",
) -> SolverResult:
    """Shared-API entry point: ``strategy`` is ``"dfs"`` (default) or ``"ids"``."""

    if strategy == "dfs":
        return solve_dfs(level, initial_state)
    if strategy == "ids":
        return solve_ids(level, initial_state)
    raise ValueError(f"unknown strategy {strategy!r}; expected one of {STRATEGIES}")


def main() -> int:
    """Run DFS or IDS for one level file and print a JSON summary."""

    parser = argparse.ArgumentParser(description="Solve a Bloxorz level with DFS or IDS.")
    parser.add_argument("level", help="Path to a .json, .txt, or .level file")
    parser.add_argument("--strategy", choices=STRATEGIES, default="dfs")
    arguments = parser.parse_args()

    result = solve(load_level(arguments.level), strategy=arguments.strategy)
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.found else 1


if __name__ == "__main__":
    raise SystemExit(main())
