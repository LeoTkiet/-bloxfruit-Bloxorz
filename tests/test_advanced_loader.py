"""Tests for the advanced-tile level format (symbols and the switches block)."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from engine.level_loader import LevelFormatError, load_level, parse_grid
from engine.tiles import SwitchKind, SwitchMode


class AdvancedSymbolTests(unittest.TestCase):
    def test_symbols_build_the_expected_layout(self) -> None:
        level = parse_grid(
            ["SFo1G", "#x#2#"],
            switches=[
                {"at": [0, 2], "mode": "toggle", "targets": [1]},
                {"at": [1, 1], "mode": "permanent_open", "targets": [2]},
            ],
        )
        tiles = level.tiles
        self.assertEqual(tiles.fragile, frozenset({(0, 1)}))
        self.assertEqual(dict(tiles.bridge_cells), {(0, 3): 1, (1, 3): 2})
        self.assertIs(tiles.switches[(0, 2)].kind, SwitchKind.SOFT)
        self.assertIs(tiles.switches[(1, 1)].kind, SwitchKind.HEAVY)
        self.assertIs(tiles.switches[(1, 1)].mode, SwitchMode.PERMANENT_OPEN)
        self.assertNotIn((0, 3), level.floor_tiles)
        self.assertIn((0, 1), level.floor_tiles)

    def test_default_mode_is_toggle_and_permanent_is_an_alias(self) -> None:
        level = parse_grid(
            ["So1G", "#x2#"],
            switches=[
                {"at": [0, 1], "targets": [1]},
                {"at": [1, 1], "mode": "permanent", "targets": [2]},
            ],
        )
        self.assertIs(level.tiles.switches[(0, 1)].mode, SwitchMode.TOGGLE)
        self.assertIs(level.tiles.switches[(1, 1)].mode, SwitchMode.PERMANENT_OPEN)

    def test_text_levels_support_fragile_and_bridges_without_switches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "adv.txt"
            path.write_text("SF1G\n", encoding="utf-8")
            level = load_level(path)
        self.assertEqual(level.tiles.fragile, frozenset({(0, 1)}))
        self.assertEqual(dict(level.tiles.bridge_cells), {(0, 2): 1})

    def test_zero_is_still_void_and_not_a_bridge(self) -> None:
        level = parse_grid(["S00G"])
        self.assertTrue(level.tiles.is_empty)
        self.assertNotIn((0, 1), level.floor_tiles)


class AdvancedFormatErrorTests(unittest.TestCase):
    def test_switch_symbol_without_configuration_is_rejected(self) -> None:
        with self.assertRaisesRegex(LevelFormatError, "has no entry"):
            parse_grid(["So1G"])

    def test_configuration_on_a_plain_tile_is_rejected(self) -> None:
        with self.assertRaisesRegex(LevelFormatError, "not marked"):
            parse_grid(["S#1G"], switches=[{"at": [0, 1], "targets": [1]}])

    def test_unknown_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(LevelFormatError, "unknown mode"):
            parse_grid(
                ["So1G"],
                switches=[{"at": [0, 1], "mode": "flip", "targets": [1]}],
            )

    def test_target_bridge_without_cells_is_rejected(self) -> None:
        with self.assertRaisesRegex(LevelFormatError, "no cells"):
            parse_grid(["So1G"], switches=[{"at": [0, 1], "targets": [2]}])

    def test_kind_must_match_the_grid_symbol(self) -> None:
        with self.assertRaisesRegex(LevelFormatError, "declares kind"):
            parse_grid(
                ["So1G"],
                switches=[{"at": [0, 1], "kind": "heavy", "targets": [1]}],
            )

    def test_malformed_position_and_targets_are_rejected(self) -> None:
        with self.assertRaisesRegex(LevelFormatError, "pair of integers"):
            parse_grid(["So1G"], switches=[{"at": "0,1", "targets": [1]}])
        with self.assertRaisesRegex(LevelFormatError, "non-empty list"):
            parse_grid(["So1G"], switches=[{"at": [0, 1], "targets": []}])

    def test_duplicate_configuration_is_rejected(self) -> None:
        entry = {"at": [0, 1], "targets": [1]}
        with self.assertRaisesRegex(LevelFormatError, "more than once"):
            parse_grid(["So1G"], switches=[entry, dict(entry)])

    def test_switches_must_be_a_list(self) -> None:
        with self.assertRaisesRegex(LevelFormatError, "list of objects"):
            parse_grid(["So1G"], switches="oops")  # type: ignore[arg-type]


class AdvancedJsonTests(unittest.TestCase):
    def test_json_level_with_switches_is_loaded(self) -> None:
        data = {
            "name": "Json advanced",
            "grid": ["S#o1#G"],
            "initial_bridge_mask": 0,
            "switches": [{"at": [0, 2], "mode": "toggle", "targets": [1]}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "adv.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            level = load_level(path)
        self.assertEqual(level.name, "Json advanced")
        self.assertIn((0, 2), level.tiles.switches)


if __name__ == "__main__":
    unittest.main()
