"""Tests for the shared JSON and text level loader."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from engine.core import Orientation
from engine.level_loader import LevelFormatError, load_level, parse_grid


class GridParserTests(unittest.TestCase):
    def test_parse_grid_builds_expected_level(self) -> None:
        level = parse_grid(["S##G"], name="Straight")
        self.assertEqual(level.name, "Straight")
        self.assertEqual(level.width, 4)
        self.assertEqual(level.height, 1)
        self.assertEqual(level.start, (0, 0))
        self.assertEqual(level.goal, (0, 3))
        self.assertEqual(level.initial_state.orientation, Orientation.STANDING)

    def test_ragged_rows_are_padded_with_void(self) -> None:
        level = parse_grid(["S##", "G"])
        self.assertEqual(level.width, 3)
        self.assertNotIn((1, 1), level.floor_tiles)

    def test_duplicate_start_is_rejected(self) -> None:
        with self.assertRaisesRegex(LevelFormatError, "exactly one start"):
            parse_grid(["SSG"])

    def test_missing_goal_is_rejected(self) -> None:
        with self.assertRaisesRegex(LevelFormatError, "exactly one goal"):
            parse_grid(["S##"])

    def test_unknown_symbol_is_rejected(self) -> None:
        with self.assertRaisesRegex(LevelFormatError, "unsupported tile symbol"):
            parse_grid(["S?G"])

    def test_non_integer_bridge_mask_is_rejected(self) -> None:
        with self.assertRaisesRegex(LevelFormatError, "must be an integer"):
            parse_grid(["S##G"], initial_bridge_mask=True)


class FileLoaderTests(unittest.TestCase):
    def test_json_level_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "level.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "JSON stage",
                        "grid": ["S##G"],
                        "initial_bridge_mask": 4,
                    }
                ),
                encoding="utf-8",
            )
            level = load_level(path)

        self.assertEqual(level.name, "JSON stage")
        self.assertEqual(level.initial_state.bridge_mask, 4)

    def test_text_level_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "straight.level"
            path.write_text("S##G\n", encoding="utf-8")
            level = load_level(path)

        self.assertEqual(level.name, "straight")
        self.assertEqual(level.floor_tiles, frozenset({(0, 0), (0, 1), (0, 2), (0, 3)}))

    def test_unsupported_extension_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stage.csv"
            path.write_text("S##G\n", encoding="utf-8")
            with self.assertRaisesRegex(LevelFormatError, "unsupported level file extension"):
                load_level(path)


if __name__ == "__main__":
    unittest.main()
