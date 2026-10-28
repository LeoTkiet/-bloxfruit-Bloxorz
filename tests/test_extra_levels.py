"""Regression tests for the split, hard and demo stages."""

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
DEMO_STAGES = sorted((LEVELS / "demo").glob("*.json"))


class ExtraLevelRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.results = {path: (load_level(path), solve(load_level(path)))
                       for path in (*SPLIT_STAGES, *HARD_STAGES)}

    def test_stage_counts(self) -> None:
        self.assertEqual(len(SPLIT_STAGES), 4)
        self.assertEqual(len(HARD_STAGES), 4)
        self.assertEqual(len(DEMO_STAGES), 7)

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


class DemoStageTests(unittest.TestCase):
    """The stages used in the demo video keep the lengths written in their files."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.results = {path.stem: (load_level(path), solve(load_level(path)),
                                   json.loads(path.read_text(encoding="utf-8")))
                       for path in DEMO_STAGES}

    def test_bfs_lengths_match_the_documented_values(self) -> None:
        for name, (_, result, data) in self.results.items():
            with self.subTest(level=name):
                expected = data.get("expected_bfs_length")
                if expected is None:
                    self.assertFalse(result.found)
                else:
                    self.assertTrue(result.found)
                    self.assertEqual(result.solution_length, expected)

    def test_split_demo_needs_a_cube_on_the_soft_switch(self) -> None:
        level, result, _ = self.results["07_split"]
        pairs = list(zip(result.states, result.states[1:]))
        self.assertTrue(any(a.is_split and b.is_split and a.bridge_mask != b.bridge_mask
                            for a, b in pairs), "a lone cube should open the bridge")
        self.assertTrue(is_goal(level, replay(level, level.initial_state, result.moves)[-1]))

    def test_showcase_has_every_tile_kind(self) -> None:
        level, result, _ = self.results["08_showcase"]
        kinds = {switch.kind.value for switch in level.tiles.switches.values()}
        self.assertEqual(kinds, {"soft", "heavy"})
        self.assertTrue(level.tiles.fragile and level.tiles.bridge_cells and level.split_switches)
        self.assertIn(True, [state.is_split for state in result.states])


if __name__ == "__main__":
    unittest.main()
