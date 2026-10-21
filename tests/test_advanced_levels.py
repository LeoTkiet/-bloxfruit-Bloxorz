"""Regression tests for the advanced stages supplied by TV2."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from engine.core import Orientation, is_goal, occupied_cells, replay
from engine.level_loader import load_level
from solvers.bfs import solve


LEVEL_DIRECTORY = Path(__file__).resolve().parents[1] / "levels" / "advanced"


class AdvancedLevelRegressionTests(unittest.TestCase):
    def test_nine_documented_advanced_cases_match_bfs_expectations(self) -> None:
        paths = sorted(LEVEL_DIRECTORY.glob("*.json"))
        self.assertEqual(len(paths), 9)

        for path in paths:
            with self.subTest(level=path.name):
                metadata = json.loads(path.read_text(encoding="utf-8"))
                expected_length = metadata["expected_bfs_length"]
                result = solve(load_level(path))

                if expected_length is None:
                    self.assertFalse(result.found)
                else:
                    self.assertTrue(result.found)
                    self.assertEqual(result.solution_length, expected_length)

    def test_no_solution_ever_stands_on_a_fragile_tile(self) -> None:
        for path in sorted(LEVEL_DIRECTORY.glob("*.json")):
            level = load_level(path)
            result = solve(level)
            if not result.found:
                continue
            with self.subTest(level=path.name):
                for state in result.states:
                    if state.orientation is Orientation.STANDING:
                        self.assertNotIn(state.position, level.tiles.fragile)

    def test_no_solution_stands_on_a_closed_bridge(self) -> None:
        for path in sorted(LEVEL_DIRECTORY.glob("*.json")):
            level = load_level(path)
            result = solve(level)
            if not result.found:
                continue
            with self.subTest(level=path.name):
                for state in result.states:
                    for cell in occupied_cells(state):
                        if cell in level.tiles.bridge_cells:
                            self.assertTrue(level.tiles.is_bridge_open(cell, state.bridge_mask))

    def test_solutions_end_standing_on_the_goal(self) -> None:
        for path in sorted(LEVEL_DIRECTORY.glob("*.json")):
            level = load_level(path)
            result = solve(level)
            if result.found:
                with self.subTest(level=path.name):
                    replayed = replay(level, level.initial_state, result.moves)
                    self.assertTrue(is_goal(level, replayed[-1]))


if __name__ == "__main__":
    unittest.main()
