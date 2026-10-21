"""Tests for the TV3 Uniform-Cost Search implementation."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from engine.core import Action, GameState, Orientation, is_goal, replay
from engine.level_loader import load_level, parse_grid
from solvers.bfs import solve as solve_bfs
from solvers.ucs import default_cost_function, solve, unit_cost_function

BASIC_LEVEL_DIR = Path(__file__).resolve().parents[1] / "levels" / "basic"


class UniformCostSearchTests(unittest.TestCase):
    def test_ucs_finds_two_move_shortest_path(self) -> None:
        level = parse_grid(["S##G"], name="Two moves")
        result = solve(level, cost_fn=unit_cost_function)
        self.assertTrue(result.found)
        self.assertEqual(result.moves, (Action.RIGHT, Action.RIGHT))
        self.assertEqual(result.solution_length, 2)
        self.assertEqual(result.path_cost, 2.0)
        self.assertTrue(is_goal(level, result.states[-1]))

    def test_ucs_returns_zero_move_solution_at_goal(self) -> None:
        level = parse_grid(["S##G"], name="Already solved")
        goal_state = GameState.standard(level.goal, Orientation.STANDING)
        result = solve(level, goal_state)
        self.assertTrue(result.found)
        self.assertEqual(result.moves, ())
        self.assertEqual(result.states, (goal_state,))
        self.assertEqual(result.expanded_nodes, 0)
        self.assertEqual(result.path_cost, 0.0)

    def test_ucs_reports_unsolvable_level(self) -> None:
        level = parse_grid(["S..G"], name="Disconnected")
        result = solve(level)
        self.assertFalse(result.found)
        self.assertEqual(result.moves, ())
        self.assertEqual(result.states, ())
        self.assertIsNone(result.path_cost)
        self.assertGreaterEqual(result.expanded_nodes, 1)

    def test_ucs_solution_replays_exactly(self) -> None:
        level = parse_grid(["####", "#S##", "###G", "####"], name="Corner")
        result = solve(level)
        self.assertTrue(result.found)
        self.assertEqual(replay(level, level.initial_state, result.moves), result.states)

    def test_ucs_unit_cost_matches_bfs_across_all_basic_levels(self) -> None:
        paths = sorted(BASIC_LEVEL_DIR.glob("*.json"))
        self.assertEqual(len(paths), 10)

        for path in paths:
            with self.subTest(level=path.name):
                level = load_level(path)
                bfs_res = solve_bfs(level)
                ucs_res = solve(level, cost_fn=unit_cost_function)

                self.assertEqual(bfs_res.found, ucs_res.found)
                if bfs_res.found:
                    self.assertEqual(ucs_res.solution_length, bfs_res.solution_length)
                    self.assertEqual(ucs_res.path_cost, float(bfs_res.solution_length))

    def test_ucs_selects_lower_cost_path_over_shorter_hop_path(self) -> None:
        """Verify that UCS optimizes total cost, not merely move count."""
        # A grid where upper detour has 4 rolls with cost 1.0 each (total 4.0),
        # but lower path has 2 rolls with cost 3.0 each (total 6.0).
        # UCS must choose the 4-roll detour because 4.0 < 6.0.
        grid = [
            "######",
            "S####G",
            "######",
        ]
        level = parse_grid(grid, name="Cost detour")

        def biased_cost(
            _lvl: Level,
            _st: GameState,
            _act: Action,
            next_st: GameState,
        ) -> float:
            # If state touches row 0, it's cheap (1.0). If it stays on row 1, it's expensive (3.0).
            if next_st.position and next_st.position[0] == 0:
                return 1.0
            return 3.0

        result = solve(level, cost_fn=biased_cost)
        self.assertTrue(result.found)
        # Verify it went through row 0
        touched_row_0 = any(st.position and st.position[0] == 0 for st in result.states)
        self.assertTrue(touched_row_0)

    def test_ucs_records_all_required_metrics(self) -> None:
        level = parse_grid(["S##G"], name="Metrics")
        result = solve(level)
        self.assertGreaterEqual(result.search_time, 0.0)
        self.assertGreaterEqual(result.peak_memory, 0)
        self.assertGreaterEqual(result.expanded_nodes, 1)
        self.assertEqual(result.solution_length, len(result.moves))
        self.assertIsNotNone(result.path_cost)
        summary = result.as_dict()
        self.assertIn("search_time", summary)
        self.assertIn("peak_memory", summary)
        self.assertIn("expanded_nodes", summary)
        self.assertIn("solution_length", summary)
        self.assertIn("path_cost", summary)


if __name__ == "__main__":
    unittest.main()
