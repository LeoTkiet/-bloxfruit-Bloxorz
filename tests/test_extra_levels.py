"""Regression tests for the split and hard benchmark stages."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from engine.core import Orientation, is_goal, occupied_cells, replay
from engine.level_loader import load_level
from solvers.bfs import solve


LEVELS = Path(__file__).resolve().parents[1] / "levels"
SPLIT_STAGES = sorted((LEVELS / "split").glob("*.json"))
HARD_STAGES = sorted((LEVELS / "hard").glob("*.json"))


class ExtraLevelRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.results = {path: (load_level(path), solve(load_level(path)))
                       for path in (*SPLIT_STAGES, *HARD_STAGES)}

    def test_stage_counts(self) -> None:
        self.assertEqual(len(SPLIT_STAGES), 4)
        self.assertEqual(len(HARD_STAGES), 4)

    def test_bfs_lengths_match_the_documented_values(self) -> None:
        for path, (_, result) in self.results.items():
            with self.subTest(level=path.name):
                expected = json.loads(path.read_text(encoding="utf-8"))["expected_bfs_length"]
                self.assertTrue(result.found)
                self.assertEqual(result.solution_length, expected)

    def test_split_stages_split_and_merge_on_the_way(self) -> None:
        for path in SPLIT_STAGES:
            _, result = self.results[path]
            with self.subTest(level=path.name):
                flags = [state.is_split for state in result.states]
                self.assertIn(True, flags)
                first = flags.index(True)
                self.assertIn(False, flags[first:])

    def test_hard_stages_need_a_wide_search(self) -> None:
        for path in HARD_STAGES:
            _, result = self.results[path]
            with self.subTest(level=path.name):
                self.assertGreaterEqual(result.solution_length, 25)
                self.assertGreaterEqual(result.expanded_nodes, 300)

    def test_solutions_respect_fragile_tiles_and_bridges(self) -> None:
        for path, (level, result) in self.results.items():
            with self.subTest(level=path.name):
                for state in result.states:
                    if state.orientation is Orientation.STANDING:
                        self.assertNotIn(state.position, level.tiles.fragile)
                    for cell in occupied_cells(state):
                        if cell in level.tiles.bridge_cells:
                            self.assertTrue(level.tiles.is_bridge_open(cell, state.bridge_mask))

    def test_solutions_replay_to_the_goal(self) -> None:
        for path, (level, result) in self.results.items():
            with self.subTest(level=path.name):
                replayed = replay(level, level.initial_state, result.moves)
                self.assertTrue(is_goal(level, replayed[-1]))


if __name__ == "__main__":
    unittest.main()
