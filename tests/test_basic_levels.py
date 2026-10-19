"""Regression tests for the ten core stages supplied by TV1."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from engine.level_loader import load_level
from solvers.bfs import solve


LEVEL_DIRECTORY = Path(__file__).resolve().parents[1] / "levels" / "basic"


class BasicLevelRegressionTests(unittest.TestCase):
    def test_ten_documented_core_cases_match_bfs_expectations(self) -> None:
        paths = sorted(LEVEL_DIRECTORY.glob("*.json"))
        self.assertEqual(len(paths), 10)

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


if __name__ == "__main__":
    unittest.main()
