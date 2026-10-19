"""Breadth-first search for unit-cost Bloxorz levels."""

from __future__ import annotations

import argparse
from collections import deque
import json
from time import perf_counter
import tracemalloc

from engine.core import Action, GameState, Level, get_successors, is_goal
from engine.level_loader import load_level

from .common import SolverResult


ParentEntry = tuple[GameState | None, Action | None]


def _reconstruct_path(
    goal_state: GameState,
    parents: dict[GameState, ParentEntry],
) -> tuple[tuple[Action, ...], tuple[GameState, ...]]:
    moves_reversed: list[Action] = []
    states_reversed = [goal_state]
    current = goal_state

    while True:
        parent, action = parents[current]
        if parent is None:
            break
        if action is None:
            raise RuntimeError("a non-root search node is missing its parent action")
        moves_reversed.append(action)
        states_reversed.append(parent)
        current = parent

    return tuple(reversed(moves_reversed)), tuple(reversed(states_reversed))


def solve(level: Level, initial_state: GameState | None = None) -> SolverResult:
    """Find a shortest unit-cost solution with breadth-first search.

    A state counts as expanded only when it is removed from the queue and its
    successors are generated. The goal node is therefore not counted as an
    expanded node. Peak memory is measured with ``tracemalloc`` around the
    complete search and path reconstruction.
    """

    start_state = initial_state if initial_state is not None else level.initial_state
    started_tracing = not tracemalloc.is_tracing()
    if started_tracing:
        tracemalloc.start()
    baseline_memory, _ = tracemalloc.get_traced_memory()
    start_time = perf_counter()

    frontier: deque[GameState] = deque([start_state])
    parents: dict[GameState, ParentEntry] = {start_state: (None, None)}
    expanded_nodes = 0
    goal_state: GameState | None = None

    try:
        while frontier:
            state = frontier.popleft()
            if is_goal(level, state):
                goal_state = state
                break

            expanded_nodes += 1
            for action, next_state, _cost in get_successors(level, state):
                if next_state in parents:
                    continue
                parents[next_state] = (state, action)
                frontier.append(next_state)

        if goal_state is None:
            moves: tuple[Action, ...] = ()
            states: tuple[GameState, ...] = ()
        else:
            moves, states = _reconstruct_path(goal_state, parents)

        search_time = perf_counter() - start_time
        _current_memory, peak_memory = tracemalloc.get_traced_memory()
        measured_peak = max(0, peak_memory - baseline_memory)
    finally:
        if started_tracing:
            tracemalloc.stop()

    if goal_state is None:
        return SolverResult(
            found=False,
            moves=(),
            states=(),
            search_time=search_time,
            peak_memory=measured_peak,
            expanded_nodes=expanded_nodes,
            solution_length=0,
            path_cost=None,
        )

    return SolverResult(
        found=True,
        moves=moves,
        states=states,
        search_time=search_time,
        peak_memory=measured_peak,
        expanded_nodes=expanded_nodes,
        solution_length=len(moves),
        path_cost=float(len(moves)),
    )


def main() -> int:
    """Run BFS for one level file and print a JSON summary."""

    parser = argparse.ArgumentParser(description="Solve a core Bloxorz level with BFS.")
    parser.add_argument("level", help="Path to a .json, .txt, or .level file")
    arguments = parser.parse_args()

    result = solve(load_level(arguments.level))
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.found else 1


if __name__ == "__main__":
    raise SystemExit(main())
