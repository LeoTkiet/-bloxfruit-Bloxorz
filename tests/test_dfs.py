"""TV2 tests for DFS and IDS: correctness, optimality, termination, state keys."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from engine.core import GameState, Orientation, is_goal, replay
from engine.level_loader import load_level, parse_grid
from solvers import bfs
from solvers.dfs import solve, solve_dfs, solve_ids


ROOT = Path(__file__).resolve().parents[1]
BASIC = sorted((ROOT / "levels" / "basic").glob("*.json"))
ADVANCED = sorted((ROOT / "levels" / "advanced").glob("*.json"))


def expected_length(path: Path) -> int | None:
    return json.loads(path.read_text(encoding="utf-8"))["expected_bfs_length"]


class DfsCorrectnessTests(unittest.TestCase):
    def test_dfs_finds_a_replayable_solution_on_every_solvable_level(self) -> None:
        for path in BASIC + ADVANCED:
            with self.subTest(level=path.name):
                level = load_level(path)
                result = solve_dfs(level)
                if expected_length(path) is None:
                    self.assertFalse(result.found)
                    continue
                self.assertTrue(result.found)
                states = replay(level, level.initial_state, result.moves)
                self.assertEqual(states, result.states)
                self.assertTrue(is_goal(level, states[-1]))

    def test_dfs_path_never_repeats_a_state(self) -> None:
        for path in BASIC + ADVANCED:
            level = load_level(path)
            result = solve_dfs(level)
            with self.subTest(level=path.name):
                self.assertEqual(len(set(result.states)), len(result.states))

    def test_dfs_matches_bfs_on_a_tiny_corridor(self) -> None:
        level = parse_grid(["S##G"])
        result = solve_dfs(level)
        reference = bfs.solve(level)
        self.assertEqual(result.moves, reference.moves)
        self.assertEqual(result.expanded_nodes, reference.expanded_nodes)

    def test_start_at_goal_is_a_zero_move_solution(self) -> None:
        level = parse_grid(["S##G"])
        at_goal = GameState.standard(level.goal, Orientation.STANDING)
        for run in (solve_dfs, solve_ids):
            with self.subTest(run=run.__name__):
                result = run(level, at_goal)
                self.assertTrue(result.found)
                self.assertEqual(result.moves, ())
                self.assertEqual(result.states, (at_goal,))
                self.assertEqual(result.expanded_nodes, 0)
                self.assertEqual(result.path_cost, 0.0)

    def test_dfs_survives_solutions_deeper_than_the_recursion_limit(self) -> None:
        length = 3 * 700  # 1400 moves > default recursion limit of 1000
        level = parse_grid(["S" + "#" * (length - 1) + "G"], name="long corridor")
        result = solve_dfs(level)
        self.assertTrue(result.found)
        self.assertEqual(result.solution_length, length // 3 * 2)


class UnsolvableTerminationTests(unittest.TestCase):
    def test_every_unsolvable_level_terminates_for_dfs_and_ids(self) -> None:
        unsolvable = [p for p in BASIC + ADVANCED if expected_length(p) is None]
        self.assertGreaterEqual(len(unsolvable), 3)
        for path in unsolvable:
            for run in (solve_dfs, solve_ids):
                with self.subTest(level=path.name, run=run.__name__):
                    result = run(load_level(path))
                    self.assertFalse(result.found)
                    self.assertEqual(result.moves, ())
                    self.assertIsNone(result.path_cost)

    def test_cyclic_state_space_does_not_loop(self) -> None:
        # A 4 x 4 open board is full of cycles; the goal is unreachable.
        # The goal sits on a tile that is disconnected from the open board.
        level = parse_grid(["S###", "####", "####", "####", "....", "...G"])
        for run in (solve_dfs, solve_ids):
            with self.subTest(run=run.__name__):
                self.assertFalse(run(level).found)


class IdsOptimalityTests(unittest.TestCase):
    def test_ids_length_equals_bfs_on_every_level(self) -> None:
        for path in BASIC + ADVANCED:
            with self.subTest(level=path.name):
                level = load_level(path)
                result = solve_ids(level)
                expected = expected_length(path)
                if expected is None:
                    self.assertFalse(result.found)
                else:
                    self.assertTrue(result.found)
                    self.assertEqual(result.solution_length, expected)
                    self.assertEqual(result.path_cost, float(expected))
                    states = replay(level, level.initial_state, result.moves)
                    self.assertTrue(is_goal(level, states[-1]))

    def test_ids_path_never_repeats_a_state(self) -> None:
        for path in ADVANCED:
            result = solve_ids(load_level(path))
            if result.found:
                with self.subTest(level=path.name):
                    self.assertEqual(len(set(result.states)), len(result.states))

    def test_max_depth_caps_the_search(self) -> None:
        level = parse_grid(["S##G"])  # needs exactly 2 moves
        self.assertFalse(solve_ids(level, max_depth=1).found)
        self.assertTrue(solve_ids(level, max_depth=2).found)

    def test_negative_max_depth_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            solve_ids(parse_grid(["S##G"]), max_depth=-1)

    def test_ids_reexpands_states_so_it_expands_at_least_as_many_as_bfs(self) -> None:
        level = load_level(BASIC[5])
        self.assertGreaterEqual(solve_ids(level).expanded_nodes, bfs.solve(level).expanded_nodes)

    def test_dfs_is_not_required_to_be_shortest_but_never_shorter_than_bfs(self) -> None:
        for path in BASIC + ADVANCED:
            level = load_level(path)
            reference = bfs.solve(level)
            result = solve_dfs(level)
            with self.subTest(level=path.name):
                self.assertEqual(result.found, reference.found)
                if result.found:
                    self.assertGreaterEqual(result.solution_length, reference.solution_length)


class StateKeyTests(unittest.TestCase):
    """Bridge flags must be part of the visited key (risk listed in the plan)."""

    def setUp(self) -> None:
        self.path = ROOT / "levels" / "advanced" / "06_permanent_return.json"
        self.level = load_level(self.path)

    def test_same_placement_with_different_masks_is_visited_twice(self) -> None:
        # The only route revisits the start placement with the bridge open.
        start = self.level.initial_state
        for run in (solve_dfs, solve_ids):
            with self.subTest(run=run.__name__):
                result = run(self.level)
                self.assertTrue(result.found)
                revisits = [
                    s
                    for s in result.states
                    if s.position == start.position and s.orientation is start.orientation
                ]
                self.assertEqual({s.bridge_mask for s in revisits}, {0, 1})

    def test_bridge_dependent_level_is_solved_with_the_required_mask_changes(self) -> None:
        level = load_level(ROOT / "levels" / "advanced" / "05_toggle_two_bridges.json")
        for run in (solve_dfs, solve_ids):
            with self.subTest(run=run.__name__):
                result = run(level)
                self.assertTrue(result.found)
                self.assertEqual(result.states[0].bridge_mask, 1)
                self.assertEqual(result.states[-1].bridge_mask, 2)


class HeavyVersusSoftLevelTests(unittest.TestCase):
    def test_heavy_switch_level_is_longer_than_its_soft_variant(self) -> None:
        data = json.loads((ROOT / "levels" / "advanced" / "04_heavy_switch_bridge.json").read_text())
        heavy = parse_grid(data["grid"], switches=data["switches"])
        soft = parse_grid([row.replace("x", "o") for row in data["grid"]], switches=data["switches"])
        self.assertEqual(solve_ids(heavy).solution_length, 10)
        self.assertLess(solve_ids(soft).solution_length, 10)


class SharedApiTests(unittest.TestCase):
    def test_solve_dispatches_by_strategy(self) -> None:
        level = parse_grid(["S##G"])
        self.assertTrue(solve(level).found)
        self.assertTrue(solve(level, strategy="dfs").found)
        self.assertTrue(solve(level, strategy="ids").found)

    def test_unknown_strategy_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown strategy"):
            solve(parse_grid(["S##G"]), strategy="bfs")

    def test_result_exposes_the_four_report_metrics(self) -> None:
        level = load_level(ADVANCED[-3])
        for run in (solve_dfs, solve_ids):
            with self.subTest(run=run.__name__):
                result = run(level)
                data = result.as_dict()
                self.assertGreaterEqual(result.search_time, 0.0)
                self.assertGreater(result.peak_memory, 0)
                self.assertGreaterEqual(result.expanded_nodes, 1)
                self.assertEqual(result.solution_length, len(result.moves))
                for key in (
                    "found",
                    "moves",
                    "search_time",
                    "peak_memory",
                    "expanded_nodes",
                    "solution_length",
                    "path_cost",
                ):
                    self.assertIn(key, data)

    def test_measurement_does_not_leave_tracemalloc_running(self) -> None:
        import tracemalloc

        solve_dfs(parse_grid(["S##G"]))
        self.assertFalse(tracemalloc.is_tracing())

    def test_solvers_do_not_mutate_the_initial_state(self) -> None:
        level = load_level(ADVANCED[2])
        before = level.initial_state
        solve_dfs(level, before)
        solve_ids(level, before)
        self.assertEqual(level.initial_state, before)


if __name__ == "__main__":
    unittest.main()
