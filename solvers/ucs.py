"""Uniform-Cost Search (UCS) for Bloxorz levels."""

from __future__ import annotations

import argparse
import heapq
from itertools import count
import json
from time import perf_counter
import tracemalloc
from typing import Callable

from engine.core import Action, GameState, Level, get_successors, is_goal, occupied_cells
from engine.level_loader import load_level

from .common import SolverResult

CostFunction = Callable[[Level, GameState, Action, GameState], float]
ParentEntry = tuple[GameState | None, Action | None]

# UCS accepts up to three extra moves to avoid one landing on thin ice.
FRAGILE_SURCHARGE = 3.0


def default_cost_function(
    level: Level,
    state: GameState,
    action: Action,
    next_state: GameState,
) -> float:
    """A realistic, non-uniform cost model for Bloxorz.

    * Standard intact rolls cost 1.0.
    * Switching between split cubes costs 0.5 (mental switch, no block translation).
    * Single cube movements cost 1.0.
    * Triggering a split switch costs 1.5 (teleportation energy).
    * A step that lands on a fragile tile costs FRAGILE_SURCHARGE more (one wrong roll
      there loses the stage). A cube resting on ice while the other one moves pays nothing.
    """

    if action is Action.SWITCH:
        return 0.5
    cost = 1.5 if not state.is_split and next_state.is_split else 1.0
    landed = set(occupied_cells(next_state)) - set(occupied_cells(state))
    if landed & level.tiles.fragile:
        cost += FRAGILE_SURCHARGE
    return cost


def unit_cost_function(
    _level: Level,
    _state: GameState,
    _action: Action,
    _next_state: GameState,
) -> float:
    """Unit-cost model where every action costs 1.0."""

    return 1.0


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


def solve(
    level: Level,
    initial_state: GameState | None = None,
    cost_fn: CostFunction | None = None,
) -> SolverResult:
    """Find a least-cost solution with Uniform-Cost Search (Dijkstra).

    Priority queue stores ``(cost, tie_breaker, state)``.
    Best-known costs are maintained in a dictionary for relaxation.
    Stale queue entries are detected and discarded on dequeue.
    The goal condition is checked upon node dequeue, guaranteeing optimality.
    Peak memory is measured with ``tracemalloc`` around search and path reconstruction.
    """

    actual_cost_fn = cost_fn if cost_fn is not None else default_cost_function
    start_state = initial_state if initial_state is not None else level.initial_state

    started_tracing = not tracemalloc.is_tracing()
    if started_tracing:
        tracemalloc.start()
    baseline_memory, _ = tracemalloc.get_traced_memory()
    start_time = perf_counter()

    counter = count()
    frontier: list[tuple[float, int, GameState]] = [(0.0, next(counter), start_state)]
    best_cost: dict[GameState, float] = {start_state: 0.0}
    parents: dict[GameState, ParentEntry] = {start_state: (None, None)}
    expanded_nodes = 0
    goal_state: GameState | None = None

    try:
        while frontier:
            current_cost, _, state = heapq.heappop(frontier)

            # Stale entry check: discard if a strictly cheaper path to state was found
            if current_cost > best_cost.get(state, float("inf")):
                continue

            if is_goal(level, state):
                goal_state = state
                break

            expanded_nodes += 1
            for action, next_state, edge_cost in get_successors(level, state):
                step_cost = actual_cost_fn(level, state, action, next_state)
                if step_cost < 0:
                    raise ValueError(f"negative edge cost {step_cost} is not permitted in UCS")

                new_cost = current_cost + step_cost
                if new_cost < best_cost.get(next_state, float("inf")):
                    best_cost[next_state] = new_cost
                    parents[next_state] = (state, action)
                    heapq.heappush(frontier, (new_cost, next(counter), next_state))

        if goal_state is None:
            moves: tuple[Action, ...] = ()
            states: tuple[GameState, ...] = ()
            final_path_cost: float | None = None
        else:
            moves, states = _reconstruct_path(goal_state, parents)
            final_path_cost = best_cost[goal_state]

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
        path_cost=final_path_cost,
    )


def main() -> int:
    """Run UCS for one level file and print a JSON summary."""

    parser = argparse.ArgumentParser(description="Solve a Bloxorz level with UCS.")
    parser.add_argument("level", help="Path to a .json, .txt, or .level file")
    parser.add_argument(
        "--unit-cost",
        action="store_true",
        help="Use unit cost (1.0 for every action)",
    )
    arguments = parser.parse_args()

    cost_fn = unit_cost_function if arguments.unit_cost else default_cost_function
    result = solve(load_level(arguments.level), cost_fn=cost_fn)
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.found else 1


if __name__ == "__main__":
    raise SystemExit(main())
