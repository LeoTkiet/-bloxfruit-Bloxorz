"""Tests for A* search, heuristics, and weighted successor costs."""

from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from collections import deque

from engine.core import Action, GameState, Orientation, get_successors, is_goal, replay
from engine.level_loader import load_level, parse_grid
from solvers.astar import astar_heuristic, relaxed_heuristic, solve, zero_heuristic
from solvers.bfs import solve as solve_bfs


LEVEL_DIRECTORY = Path(__file__).resolve().parents[1] / "levels" / "basic"
ALL_STAGES = sorted((Path(__file__).resolve().parents[1] / "levels").glob("*/*.json"))
SMALL_STAGES = [path for path in ALL_STAGES if path.parent.name != "split"] + sorted(
    (Path(__file__).resolve().parents[1] / "levels" / "split").glob("01_*.json")
)


def exact_costs_to_goal(level):
    """Unit-cost distance to the goal for every state reachable from the start."""

    seen = {level.initial_state}
    queue = deque(seen)
    predecessors: dict[GameState, list[GameState]] = {}
    while queue:
        state = queue.popleft()
        for _, next_state, _ in get_successors(level, state):
            predecessors.setdefault(next_state, []).append(state)
            if next_state not in seen:
                seen.add(next_state)
                queue.append(next_state)
    costs = {state: 0 for state in seen if is_goal(level, state)}
    queue = deque(costs)
    while queue:
        state = queue.popleft()
        for previous in predecessors.get(state, ()):
            if previous not in costs:
                costs[previous] = costs[state] + 1
                queue.append(previous)
    return seen, costs


class AStarTests(unittest.TestCase):
    def test_astar_finds_optimal_core_solution(self) -> None:
        level = parse_grid(["S##G"], name="Two moves")
        result = solve(level)

        self.assertTrue(result.found)
        self.assertEqual(result.moves, (Action.RIGHT, Action.RIGHT))
        self.assertEqual(result.solution_length, 2)
        self.assertEqual(result.path_cost, 2.0)
        self.assertTrue(is_goal(level, result.states[-1]))
        self.assertEqual(replay(level, level.initial_state, result.moves), result.states)

    def test_astar_uses_successor_costs_and_updates_best_g(self) -> None:
        level = parse_grid(["S##G"], name="Weighted graph")
        start = GameState.standard((0, 0))
        expensive = GameState.standard((0, 1))
        detour = GameState.standard((1, 0))
        goal = GameState.standard((0, 3))
        graph = {
            start: [
                (Action.RIGHT, expensive, 4),
                (Action.DOWN, detour, 1),
            ],
            expensive: [(Action.RIGHT, goal, 1)],
            detour: [(Action.RIGHT, expensive, 1)],
            goal: [],
        }

        with patch(
            "solvers.astar.get_successors",
            side_effect=lambda _level, state: graph[state],
        ):
            result = solve(level, start, heuristic=zero_heuristic)

        self.assertTrue(result.found)
        self.assertEqual(result.states, (start, detour, expensive, goal))
        self.assertEqual(result.path_cost, 3.0)

    def test_astar_reports_unsolvable_level(self) -> None:
        level = parse_grid(["S..G"], name="Disconnected")
        result = solve(level)

        self.assertFalse(result.found)
        self.assertEqual(result.moves, ())
        self.assertEqual(result.states, ())
        self.assertIsNone(result.path_cost)

    def test_astar_returns_zero_move_solution(self) -> None:
        level = parse_grid(["S##G"], name="Already solved")
        goal_state = GameState.standard(level.goal, Orientation.STANDING)

        result = solve(level, goal_state)

        self.assertTrue(result.found)
        self.assertEqual(result.states, (goal_state,))
        self.assertEqual(result.path_cost, 0.0)

    def test_geometric_heuristic_is_zero_for_split_states(self) -> None:
        level = parse_grid(["S##G"], name="Split fallback")
        split_state = GameState.split(((0, 0), (0, 1)))

        self.assertEqual(astar_heuristic(level, split_state), 0.0)
        self.assertEqual(zero_heuristic(level, level.initial_state), 0.0)

    def test_mock_teleport_requires_zero_heuristic_for_whole_search(self) -> None:
        level = parse_grid(["S#####G"], name="Mock TV3 teleport")
        start = level.initial_state
        split_state = GameState.split(((1, 1), (1, 2)))
        goal = GameState.standard(level.goal, Orientation.STANDING)
        graph = {
            start: [(Action.RIGHT, split_state, 1)],
            split_state: [(Action.LEFT, goal, 1)],
            goal: [],
        }

        with (
            patch(
                "solvers.astar.get_successors",
                side_effect=lambda _level, state: graph[state],
            ),
            patch(
                "solvers.astar.is_goal",
                side_effect=lambda _level, state: state == goal,
            ),
        ):
            result = solve(level)

        self.assertEqual(astar_heuristic(level, start), 3.0)
        self.assertTrue(result.found)
        self.assertEqual(result.states, (start, split_state, goal))
        self.assertEqual(result.path_cost, 2.0)

    def test_default_heuristic_minimizes_cost_not_number_of_moves(self) -> None:
        level = parse_grid(["######", "S####G", "######"], name="Cost detour")
        start = GameState.standard((1, 0))
        expensive = GameState.standard((1, 1))
        cheap_first = GameState.standard((0, 0))
        cheap_second = GameState.standard((0, 1))
        cheap_third = GameState.standard((0, 2))
        goal = GameState.standard(level.goal)
        graph = {
            start: [
                (Action.RIGHT, expensive, 1.0),
                (Action.UP, cheap_first, 1.0),
            ],
            expensive: [(Action.RIGHT, goal, 1.0)],
            cheap_first: [(Action.RIGHT, cheap_second, 1.0)],
            cheap_second: [(Action.RIGHT, cheap_third, 1.0)],
            cheap_third: [(Action.DOWN, goal, 1.0)],
            goal: [],
        }
        expensive_transitions = {(start, expensive), (expensive, goal)}

        def biased_cost(_level, state, _action, next_state):
            return 3.0 if (state, next_state) in expensive_transitions else 1.0

        with patch(
            "solvers.astar.get_successors",
            side_effect=lambda _level, state: graph[state],
        ):
            result = solve(level, start, cost_fn=biased_cost)

        self.assertTrue(result.found)
        self.assertEqual(result.solution_length, 4)
        self.assertEqual(result.path_cost, 4.0)
        self.assertEqual(
            result.states,
            (start, cheap_first, cheap_second, cheap_third, goal),
        )

    def test_astar_rejects_negative_edge_cost(self) -> None:
        level = parse_grid(["S##G"], name="Invalid cost")
        successor = GameState.standard((0, 1), Orientation.HORIZONTAL)

        with patch(
            "solvers.astar.get_successors",
            return_value=[(Action.RIGHT, successor, -1)],
        ):
            with self.assertRaisesRegex(ValueError, "successor costs"):
                solve(level)

    def test_astar_matches_all_basic_level_expectations(self) -> None:
        for path in sorted(LEVEL_DIRECTORY.glob("*.json")):
            with self.subTest(level=path.name):
                expected_length = json.loads(
                    path.read_text(encoding="utf-8")
                )["expected_bfs_length"]
                result = solve(load_level(path))

                if expected_length is None:
                    self.assertFalse(result.found)
                else:
                    self.assertTrue(result.found)
                    self.assertEqual(result.solution_length, expected_length)


class RelaxedHeuristicTests(unittest.TestCase):
    def test_relaxed_distance_counts_rolls_and_orientation(self) -> None:
        level = parse_grid(["#######", "#S#####", "####G##", "#######"], name="Open board")
        lying_on_goal = GameState.standard(level.goal, Orientation.HORIZONTAL)

        self.assertEqual(relaxed_heuristic(level, level.initial_state), 3.0)
        self.assertEqual(astar_heuristic(level, level.initial_state), 2.0)
        self.assertEqual(relaxed_heuristic(level, lying_on_goal), 4.0)
        self.assertEqual(astar_heuristic(level, lying_on_goal), 0.0)
        self.assertEqual(relaxed_heuristic(level, GameState.standard(level.goal)), 0.0)

    def test_relaxed_board_opens_bridges_and_ignores_fragile(self) -> None:
        bridge = parse_grid(["S#1G"], name="Closed bridge")
        fragile = parse_grid(["S##F##G"], name="Fragile stop")

        self.assertFalse(solve(bridge).found)
        self.assertEqual(relaxed_heuristic(bridge, bridge.initial_state), 2.0)
        self.assertFalse(solve(fragile).found)
        self.assertEqual(relaxed_heuristic(fragile, fragile.initial_state), 4.0)

    def test_split_switches_are_targets_and_split_states_get_zero(self) -> None:
        level = load_level(ALL_STAGES[0].parents[1] / "split" / "01_split_intro.json")
        on_switch = GameState.standard((0, 3))

        self.assertEqual(relaxed_heuristic(level, on_switch), 0.0)
        self.assertEqual(relaxed_heuristic(level, GameState.split(((2, 0), (2, 2)))), 0.0)

    def test_relaxed_heuristic_is_admissible_and_consistent_on_every_stage(self) -> None:
        for path in SMALL_STAGES:
            level = load_level(path)
            seen, costs = exact_costs_to_goal(level)
            with self.subTest(level=path.name):
                for state in seen:
                    estimate = relaxed_heuristic(level, state)
                    if state in costs:
                        self.assertLessEqual(estimate, costs[state])
                    for _, next_state, cost in get_successors(level, state):
                        self.assertLessEqual(estimate, cost + relaxed_heuristic(level, next_state))

    def test_relaxed_heuristic_dominates_the_geometric_bound(self) -> None:
        for path in SMALL_STAGES:
            level = load_level(path)
            if level.split_switches:
                continue
            seen, costs = exact_costs_to_goal(level)
            with self.subTest(level=path.name):
                for state in costs:
                    self.assertGreaterEqual(
                        relaxed_heuristic(level, state), astar_heuristic(level, state)
                    )

    def test_relaxed_astar_is_optimal_and_expands_less_on_every_stage(self) -> None:
        for path in ALL_STAGES:
            level = load_level(path)
            with self.subTest(level=path.name):
                guided = solve(level, heuristic=relaxed_heuristic)
                breadth = solve_bfs(level)
                self.assertEqual(guided.found, breadth.found)
                self.assertEqual(guided.solution_length, breadth.solution_length)
                if not level.split_switches:
                    self.assertLessEqual(
                        guided.expanded_nodes,
                        solve(level, heuristic=astar_heuristic).expanded_nodes,
                    )


if __name__ == "__main__":
    unittest.main()
