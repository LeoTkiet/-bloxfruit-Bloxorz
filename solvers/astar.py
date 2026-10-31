"""A* search for Bloxorz levels."""

from __future__ import annotations

import argparse
from collections import deque
from heapq import heappop, heappush
import json
import math
from numbers import Real
from time import perf_counter
import tracemalloc
from typing import Callable

from engine.core import (
    ACTION_ORDER,
    Action,
    GameState,
    Level,
    Orientation,
    Position,
    get_successors,
    is_goal,
    occupied_cells,
    roll,
)
from engine.level_loader import load_level

from .common import ParentEntry, SolverResult, reconstruct_path


Heuristic = Callable[[Level, GameState], float]
CostFunction = Callable[[Level, GameState, Action, GameState], Real]


def astar_heuristic(level: Level, state: GameState) -> float:
    """Estimate remaining core rolls with a geometric lower bound.

    For intact blocks, one roll changes the anchor by at most two Manhattan
    cells. This is admissible only when every movement roll costs at least one
    and no reachable transition can teleport or otherwise move the block
    without paying for the corresponding distance. Use it only for core-only
    levels; the default heuristic is safe for TV3's weighted and split moves.
    """

    if state.is_split or state.position is None:
        return 0.0

    distance = abs(state.position[0] - level.goal[0]) + abs(
        state.position[1] - level.goal[1]
    )
    return float((distance + 1) // 2)


def zero_heuristic(_level: Level, _state: GameState) -> float:
    """Return a safe zero estimate for modes without a proven lower bound."""

    return 0.0


_RELAXED_CACHE: dict[int, tuple[Level, dict[tuple[Position, Orientation], int]]] = {}


def _relaxed_distances(level: Level) -> dict[tuple[Position, Orientation], int]:
    """Roll distances to the nearest target on the relaxed board, keyed by placement.

    The relaxed board keeps the void cells but opens every bridge and forgets the
    fragile rule, so switches no longer matter. The targets are the goal and every
    split switch, all standing. Every roll can be undone by the opposite roll, so a
    breadth-first search outward from the targets gives the distance *to* them.
    """

    cached = _RELAXED_CACHE.get(id(level))
    if cached is not None and cached[0] is level:
        return cached[1]

    supported = level.floor_tiles | frozenset(level.tiles.bridge_cells)
    distances: dict[tuple[Position, Orientation], int] = {}
    queue: deque[GameState] = deque()
    for cell in (level.goal, *level.split_switch_map):
        if (cell, Orientation.STANDING) not in distances:
            distances[(cell, Orientation.STANDING)] = 0
            queue.append(GameState.standard(cell, Orientation.STANDING))

    while queue:
        state = queue.popleft()
        distance = distances[(state.position, state.orientation)] + 1
        for action in ACTION_ORDER:
            neighbour = roll(state, action)
            key = (neighbour.position, neighbour.orientation)
            if key in distances or not all(
                cell in supported for cell in occupied_cells(neighbour)
            ):
                continue
            distances[key] = distance
            queue.append(neighbour)

    if len(_RELAXED_CACHE) >= 8:
        _RELAXED_CACHE.clear()
    _RELAXED_CACHE[id(level)] = (level, distances)
    return distances


def relaxed_heuristic(level: Level, state: GameState) -> float:
    """Exact number of rolls to the goal on a relaxed copy of the board.

    Every real move is also legal on the relaxed board (all bridges open, no
    fragile rule), so its distance never overestimates when each roll costs at
    least one; being an exact shortest-path distance it is also consistent. A
    split switch counts as a target because its teleport is free to the cubes:
    an intact block either reaches the goal or first stands on a split switch.
    Split states get 0. The table is built once per level, on the first call.
    """

    if state.is_split or state.position is None:
        return 0.0
    # placements cut off from every target cannot reach the goal on the real board either
    return float(_relaxed_distances(level).get((state.position, state.orientation), 0))


def _validated_heuristic(heuristic: Heuristic, level: Level, state: GameState) -> float:
    estimate = heuristic(level, state)
    if not isinstance(estimate, Real) or isinstance(estimate, bool):
        raise ValueError("heuristic values must be finite non-negative numbers")
    estimate = float(estimate)
    if not math.isfinite(estimate) or estimate < 0:
        raise ValueError("heuristic values must be finite non-negative numbers")
    return estimate


def _validated_cost(cost: Real) -> float:
    if not isinstance(cost, Real) or isinstance(cost, bool):
        raise ValueError("successor costs must be finite non-negative numbers")
    value = float(cost)
    if not math.isfinite(value) or value < 0:
        raise ValueError("successor costs must be finite non-negative numbers")
    return value


def solve(
    level: Level,
    initial_state: GameState | None = None,
    heuristic: Heuristic = zero_heuristic,
    cost_fn: CostFunction | None = None,
) -> SolverResult:
    """Find a least-cost solution using A* and the engine's successor costs.

    The default zero heuristic preserves optimality for arbitrary non-negative
    successor costs and transitions, including TV3's split/teleport rules.
    Supply ``relaxed_heuristic`` for any level whose rolls cost at least one,
    or ``astar_heuristic`` only for core-only levels where its geometric
    lower-bound assumptions hold. If ``cost_fn`` is supplied, it overrides the
    cost in each successor tuple.
    """

    start_state = initial_state if initial_state is not None else level.initial_state
    started_tracing = not tracemalloc.is_tracing()
    if started_tracing:
        tracemalloc.start()
    baseline_memory, _ = tracemalloc.get_traced_memory()
    start_time = perf_counter()

    goal_state: GameState | None = None
    expanded_nodes = 0

    try:
        sequence = 0
        frontier: list[tuple[float, int, float, GameState]] = []
        start_h = _validated_heuristic(heuristic, level, start_state)
        heappush(frontier, (start_h, sequence, 0.0, start_state))
        best_g: dict[GameState, float] = {start_state: 0.0}
        parents: dict[GameState, ParentEntry] = {start_state: (None, None)}

        while frontier:
            _f_score, _sequence, g_score, state = heappop(frontier)
            if g_score != best_g.get(state):
                continue

            if is_goal(level, state):
                goal_state = state
                break

            expanded_nodes += 1
            for action, next_state, edge_cost in get_successors(level, state):
                transition_cost = (
                    edge_cost
                    if cost_fn is None
                    else cost_fn(level, state, action, next_state)
                )
                candidate_g = g_score + _validated_cost(transition_cost)
                if candidate_g >= best_g.get(next_state, math.inf):
                    continue

                best_g[next_state] = candidate_g
                parents[next_state] = (state, action)
                estimate = _validated_heuristic(heuristic, level, next_state)
                sequence += 1
                heappush(
                    frontier,
                    (candidate_g + estimate, sequence, candidate_g, next_state),
                )

        if goal_state is None:
            moves: tuple[Action, ...] = ()
            states: tuple[GameState, ...] = ()
            path_cost: float | None = None
        else:
            moves, states = reconstruct_path(goal_state, parents)
            path_cost = best_g[goal_state]

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
        path_cost=path_cost,
    )


def main() -> int:
    """Run A* for one level file and print a JSON summary."""

    parser = argparse.ArgumentParser(description="Solve a Bloxorz level with A*.")
    parser.add_argument("level", help="Path to a .json, .txt, or .level file")
    heuristic_group = parser.add_mutually_exclusive_group()
    heuristic_group.add_argument(
        "--zero-heuristic",
        action="store_true",
        help="Use the safe h=0 heuristic (the default)",
    )
    heuristic_group.add_argument(
        "--core-geometric-heuristic",
        action="store_true",
        help="Use the geometric heuristic for compatible core-only levels",
    )
    heuristic_group.add_argument(
        "--relaxed-heuristic",
        action="store_true",
        help="Use the relaxed-board distance (admissible on every stage)",
    )
    arguments = parser.parse_args()

    if arguments.relaxed_heuristic:
        heuristic = relaxed_heuristic
    elif arguments.core_geometric_heuristic:
        heuristic = astar_heuristic
    else:
        heuristic = zero_heuristic
    result = solve(load_level(arguments.level), heuristic=heuristic)
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.found else 1


if __name__ == "__main__":
    raise SystemExit(main())
