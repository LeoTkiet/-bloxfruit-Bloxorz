"""Tests for the TV3 Uniform-Cost Search implementation."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from engine.core import Action, GameState, Orientation, is_goal, replay
from engine.level_loader import load_level, parse_grid
from solvers.bfs import solve as solve_bfs
from solvers.ucs import FRAGILE_SURCHARGE, default_cost_function, solve, unit_cost_function

LEVELS = Path(__file__).resolve().parents[1] / "levels"
BASIC_LEVEL_DIR = LEVELS / "basic"


def route_cost(level, result) -> float:
    steps = zip(result.states, result.moves, result.states[1:])
    return sum(default_cost_function(level, state, move, after) for state, move, after in steps)


class FragileCostTests(unittest.TestCase):
    """Landing on thin ice is what separates the UCS cost from counting moves."""

    def setUp(self) -> None:
        self.level = parse_grid(["S###", "##FF", "###G"], name="Ice")

    def cost(self, state, action, next_state) -> float:
        return default_cost_function(self.level, state, action, next_state)

    def test_a_roll_costs_one_and_landing_on_ice_costs_the_surcharge_more(self) -> None:
        start = GameState.standard((0, 0), Orientation.STANDING)
        floor = GameState.standard((0, 1), Orientation.HORIZONTAL)
        self.assertEqual(self.cost(start, Action.RIGHT, floor), 1.0)
        before = GameState.standard((1, 1), Orientation.STANDING)
        ice = GameState.standard((1, 2), Orientation.HORIZONTAL)
        self.assertEqual(self.cost(before, Action.RIGHT, ice), 1.0 + FRAGILE_SURCHARGE)

    def test_one_step_pays_once_even_when_only_half_of_the_block_is_on_ice(self) -> None:
        before = GameState.standard((0, 1), Orientation.VERTICAL)
        half = GameState.standard((0, 2), Orientation.VERTICAL)
        self.assertEqual(self.cost(before, Action.RIGHT, half), 1.0 + FRAGILE_SURCHARGE)

    def test_a_cube_resting_on_ice_pays_nothing(self) -> None:
        resting = GameState.split(((0, 0), (1, 2)))
        moved = GameState.split(((0, 1), (1, 2)))
        self.assertEqual(self.cost(resting, Action.RIGHT, moved), 1.0)
        self.assertEqual(self.cost(resting, Action.SWITCH, resting), 0.5)

    def test_a_cube_stepping_onto_ice_pays_the_surcharge(self) -> None:
        before = GameState.split(((0, 0), (1, 1)))
        after = GameState.split(((0, 0), (1, 2)))
        self.assertEqual(self.cost(before, Action.RIGHT, after), 1.0 + FRAGILE_SURCHARGE)

    def test_a_split_costs_more_and_a_cube_thrown_onto_ice_adds_the_surcharge(self) -> None:
        whole = GameState.standard((0, 3), Orientation.STANDING)
        on_floor = GameState.split(((0, 0), (0, 1)))
        on_ice = GameState.split(((0, 0), (1, 2)))
        self.assertEqual(self.cost(whole, Action.UP, on_floor), 1.5)
        self.assertEqual(self.cost(whole, Action.UP, on_ice), 1.5 + FRAGILE_SURCHARGE)

    def test_ucs_takes_more_moves_to_avoid_ice_on_a_stage_where_bfs_does_not(self) -> None:
        level = load_level(LEVELS / "advanced" / "02_fragile_band.json")
        shortest, cheapest = solve_bfs(level), solve(level)
        self.assertEqual((shortest.solution_length, route_cost(level, shortest)), (6, 12.0))
        self.assertEqual((cheapest.solution_length, cheapest.path_cost), (8, 11.0))

    def test_ucs_finds_a_cheaper_route_of_the_same_length(self) -> None:
        level = load_level(LEVELS / "hard" / "02_fragile_bands.json")
        shortest, cheapest = solve_bfs(level), solve(level)
        self.assertEqual(cheapest.solution_length, shortest.solution_length)
        self.assertLess(cheapest.path_cost, route_cost(level, shortest))

    def test_without_ice_on_the_board_the_cost_is_the_number_of_moves(self) -> None:
        level = load_level(LEVELS / "hard" / "01_grand_maze.json")
        result = solve(level)
        self.assertEqual(result.path_cost, float(solve_bfs(level).solution_length))


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
