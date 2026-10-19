"""Tests for the TV1 breadth-first search implementation and metrics."""

from __future__ import annotations

import unittest

from engine.core import Action, GameState, Orientation, is_goal, replay
from engine.level_loader import parse_grid
from solvers.bfs import solve


class BreadthFirstSearchTests(unittest.TestCase):
    def test_bfs_finds_two_move_shortest_path(self) -> None:
        level = parse_grid(["S##G"], name="Two moves")
        result = solve(level)
        self.assertTrue(result.found)
        self.assertEqual(result.moves, (Action.RIGHT, Action.RIGHT))
        self.assertEqual(result.solution_length, 2)
        self.assertEqual(result.path_cost, 2.0)
        self.assertTrue(is_goal(level, result.states[-1]))

    def test_bfs_returns_zero_move_solution_at_goal(self) -> None:
        level = parse_grid(["S##G"], name="Already solved")
        goal_state = GameState.standard(level.goal, Orientation.STANDING)
        result = solve(level, goal_state)
        self.assertTrue(result.found)
        self.assertEqual(result.moves, ())
        self.assertEqual(result.states, (goal_state,))
        self.assertEqual(result.expanded_nodes, 0)

    def test_bfs_reports_unsolvable_level(self) -> None:
        level = parse_grid(["S..G"], name="Disconnected")
        result = solve(level)
        self.assertFalse(result.found)
        self.assertEqual(result.moves, ())
        self.assertEqual(result.states, ())
        self.assertIsNone(result.path_cost)
        self.assertGreaterEqual(result.expanded_nodes, 1)

    def test_bfs_solution_replays_exactly(self) -> None:
        level = parse_grid(["####", "#S##", "###G", "####"], name="Corner")
        result = solve(level)
        self.assertTrue(result.found)
        self.assertEqual(replay(level, level.initial_state, result.moves), result.states)

    def test_bfs_keeps_bridge_mask_in_state_keys(self) -> None:
        level = parse_grid(["S##G"], name="Bridge mask", initial_bridge_mask=7)
        result = solve(level)
        self.assertTrue(result.found)
        self.assertTrue(all(state.bridge_mask == 7 for state in result.states))

    def test_bfs_records_required_metrics(self) -> None:
        level = parse_grid(["S##G"], name="Metrics")
        result = solve(level)
        self.assertGreaterEqual(result.search_time, 0.0)
        self.assertGreaterEqual(result.peak_memory, 0)
        self.assertGreaterEqual(result.expanded_nodes, 1)
        self.assertEqual(result.solution_length, len(result.moves))
        self.assertEqual(result.as_dict()["moves"], ["right", "right"])


if __name__ == "__main__":
    unittest.main()
