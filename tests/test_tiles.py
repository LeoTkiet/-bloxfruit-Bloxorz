"""TV2 tests for fragile tiles, bridges, soft/heavy switches and switch modes.

Every tile or switch kind has at least one valid and one invalid case.
"""

from __future__ import annotations

import unittest

from engine.core import (
    Action,
    GameState,
    Level,
    Orientation,
    is_state_supported,
    occupied_cells,
    replay,
    try_move,
)
from engine.level_loader import parse_grid
from engine.tiles import (
    EMPTY_LAYOUT,
    Switch,
    SwitchKind,
    SwitchMode,
    TileLayout,
    bridge_bit,
)


def toggle(position: tuple[int, int], *targets: int) -> dict:
    return {"at": list(position), "mode": "toggle", "targets": list(targets)}


def standing(position: tuple[int, int], mask: int = 0) -> GameState:
    return GameState.standard(position, Orientation.STANDING, mask)


class FragileTileTests(unittest.TestCase):
    def test_lying_horizontal_block_may_rest_on_fragile_tiles(self) -> None:
        level = parse_grid(["SFF#G"])
        state = try_move(level, level.initial_state, Action.RIGHT)
        self.assertIsNotNone(state)
        self.assertEqual(occupied_cells(state), ((0, 1), (0, 2)))

    def test_lying_vertical_block_may_rest_on_fragile_tiles(self) -> None:
        level = parse_grid(["S", "F", "F", "#", "G"])
        state = try_move(level, level.initial_state, Action.DOWN)
        self.assertIsNotNone(state)
        self.assertEqual(state.orientation, Orientation.VERTICAL)

    def test_standing_block_on_fragile_tile_is_rejected(self) -> None:
        level = parse_grid(["S##F#G"])
        lying = try_move(level, level.initial_state, Action.RIGHT)
        self.assertIsNotNone(lying)
        self.assertIsNone(try_move(level, lying, Action.RIGHT))  # would stand on (0, 3)

    def test_standing_support_check_distinguishes_orientation(self) -> None:
        level = parse_grid(["S#F#G"])
        self.assertFalse(is_state_supported(level, standing((0, 2))))
        lying = GameState.standard((0, 1), Orientation.HORIZONTAL)
        self.assertTrue(is_state_supported(level, lying))

    def test_fragile_tile_is_ordinary_floor_for_support(self) -> None:
        level = parse_grid(["S#F#G"])
        self.assertIn((0, 2), level.floor_tiles)
        self.assertIn((0, 2), level.tiles.fragile)

    def test_start_and_goal_cannot_be_fragile(self) -> None:
        layout = TileLayout(fragile=frozenset({(0, 0)}))
        with self.assertRaisesRegex(ValueError, "start and goal"):
            Level(
                name="bad",
                width=3,
                height=1,
                floor_tiles=frozenset({(0, 0), (0, 1), (0, 2)}),
                start=(0, 0),
                goal=(0, 2),
                tiles=layout,
            )


class BridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        # Bridge 1 occupies (0, 2) and (0, 3); switch o at (0, 7) is far away.
        self.level = parse_grid(["S#11#G"])

    def test_closed_bridge_behaves_like_void(self) -> None:
        lying = try_move(self.level, self.level.initial_state, Action.RIGHT)
        self.assertIsNone(lying)  # would cover bridge cell (0, 2)

    def test_open_bridge_can_be_crossed(self) -> None:
        open_start = standing((0, 0), mask=bridge_bit(1))
        lying = try_move(self.level, open_start, Action.RIGHT)
        self.assertIsNotNone(lying)
        self.assertEqual(lying.bridge_mask, 1)

    def test_bridge_ids_use_independent_mask_bits(self) -> None:
        level = parse_grid(["S#12#G"])
        only_bridge_two = standing((0, 0), mask=bridge_bit(2))
        self.assertIsNone(try_move(level, only_bridge_two, Action.RIGHT))
        both = standing((0, 0), mask=bridge_bit(1) | bridge_bit(2))
        self.assertIsNotNone(try_move(level, both, Action.RIGHT))

    def test_bridge_mask_is_part_of_state_identity(self) -> None:
        closed = standing((0, 0), mask=0)
        opened = standing((0, 0), mask=1)
        self.assertNotEqual(closed, opened)
        self.assertEqual(len({closed, opened}), 2)

    def test_bridge_cells_are_not_floor(self) -> None:
        self.assertNotIn((0, 2), self.level.floor_tiles)
        self.assertEqual(self.level.tiles.bridge_cells[(0, 2)], 1)

    def test_bridge_id_range_is_validated(self) -> None:
        with self.assertRaises(ValueError):
            bridge_bit(0)
        with self.assertRaises(ValueError):
            bridge_bit(10)


class SoftSwitchTests(unittest.TestCase):
    def setUp(self) -> None:
        # S(0,0) #(0,1) o(0,2) bridge-1 at (0,3) #(0,4) G(0,5)
        self.level = parse_grid(["S#o1#G"], switches=[toggle((0, 2), 1)])

    def test_lying_block_covering_a_soft_switch_fires_it(self) -> None:
        lying = try_move(self.level, self.level.initial_state, Action.RIGHT)
        self.assertIsNotNone(lying)
        self.assertEqual(lying.bridge_mask, 1)

    def test_standing_block_on_a_soft_switch_fires_it(self) -> None:
        level = parse_grid(["S##o1G"], switches=[toggle((0, 3), 1)])
        lying = try_move(level, level.initial_state, Action.RIGHT)
        self.assertEqual(lying.bridge_mask, 0)  # (0,1),(0,2) cover no switch
        landed = try_move(level, lying, Action.RIGHT)
        self.assertEqual(landed.bridge_mask, 1)

    def test_placement_not_touching_the_switch_changes_nothing(self) -> None:
        level = parse_grid(["S#o1#G", "#####.", "#####."], switches=[toggle((0, 2), 1)])
        down = try_move(level, level.initial_state, Action.DOWN)
        self.assertIsNotNone(down)
        self.assertEqual(down.bridge_mask, 0)


class HeavySwitchTests(unittest.TestCase):
    def setUp(self) -> None:
        # S(0,0) #(0,1) #(0,2) x(0,3) bridge-1 at (0,4) G(0,5)
        self.level = parse_grid(["S##x1G"], switches=[toggle((0, 3), 1)])

    def test_standing_block_fires_a_heavy_switch(self) -> None:
        lying = try_move(self.level, self.level.initial_state, Action.RIGHT)
        landed = try_move(self.level, lying, Action.RIGHT)
        self.assertEqual(landed.orientation, Orientation.STANDING)
        self.assertEqual(landed.position, (0, 3))
        self.assertEqual(landed.bridge_mask, 1)

    def test_lying_block_does_not_fire_a_heavy_switch(self) -> None:
        from_left = standing((0, 1))
        covering = try_move(self.level, from_left, Action.RIGHT)  # (0,2) and (0,3)
        self.assertIsNotNone(covering)
        self.assertIn((0, 3), occupied_cells(covering))
        self.assertEqual(covering.bridge_mask, 0)

    def test_soft_and_heavy_differ_on_the_same_placement(self) -> None:
        soft_level = parse_grid(["S##o1G"], switches=[toggle((0, 3), 1)])
        covering = try_move(soft_level, standing((0, 1)), Action.RIGHT)
        self.assertEqual(covering.bridge_mask, 1)


class SwitchModeTests(unittest.TestCase):
    def switch(self, mode: SwitchMode, *targets: int) -> Switch:
        return Switch((0, 0), SwitchKind.SOFT, mode, targets)

    def test_toggle_flips_every_time(self) -> None:
        switch = self.switch(SwitchMode.TOGGLE, 1)
        self.assertEqual(switch.apply(0), 1)
        self.assertEqual(switch.apply(1), 0)
        self.assertEqual(switch.apply(switch.apply(0)), 0)

    def test_toggle_flips_all_targets_and_keeps_other_bits(self) -> None:
        switch = self.switch(SwitchMode.TOGGLE, 1, 2)
        self.assertEqual(switch.apply(0b100), 0b111)
        self.assertEqual(switch.apply(0b101), 0b110)

    def test_permanent_open_never_closes(self) -> None:
        switch = self.switch(SwitchMode.PERMANENT_OPEN, 1)
        once = switch.apply(0)
        self.assertEqual(once, 1)
        self.assertEqual(switch.apply(once), 1)

    def test_permanent_close_never_reopens(self) -> None:
        switch = self.switch(SwitchMode.PERMANENT_CLOSE, 1)
        once = switch.apply(1)
        self.assertEqual(once, 0)
        self.assertEqual(switch.apply(once), 0)

    def test_switch_needs_at_least_one_valid_target(self) -> None:
        with self.assertRaises(ValueError):
            Switch((0, 0), SwitchKind.SOFT, SwitchMode.TOGGLE, ())
        with self.assertRaises(ValueError):
            Switch((0, 0), SwitchKind.SOFT, SwitchMode.TOGGLE, (12,))

    def test_repeated_presses_in_a_level_toggle_back_and_forth(self) -> None:
        grid = ["###1", "#S##", "#o##", "#G##"]
        level = parse_grid(grid, switches=[toggle((2, 1), 1)])
        down, up = Action.DOWN, Action.UP
        states = replay(level, level.initial_state, [down, up, down])
        self.assertEqual([s.bridge_mask for s in states], [0, 1, 1, 0])

    def test_repeated_presses_of_a_permanent_switch_stay_open(self) -> None:
        grid = ["###1", "#S##", "#o##", "#G##"]
        permanent = {"at": [2, 1], "mode": "permanent_open", "targets": [1]}
        level = parse_grid(grid, switches=[permanent])
        states = replay(level, level.initial_state, [Action.DOWN, Action.UP, Action.DOWN])
        self.assertEqual([s.bridge_mask for s in states], [0, 1, 1, 1])

    def test_permanent_close_switch_seals_a_bridge(self) -> None:
        grid = ["###1", "#S##", "#o##", "#G##"]
        sealing = {"at": [2, 1], "mode": "permanent_close", "targets": [1]}
        level = parse_grid(grid, switches=[sealing], initial_bridge_mask=1)
        states = replay(level, level.initial_state, [Action.DOWN, Action.UP, Action.DOWN])
        self.assertEqual([s.bridge_mask for s in states], [1, 0, 0, 0])

    def test_one_move_fires_each_switch_once_in_row_major_order(self) -> None:
        layout = TileLayout(
            bridge_cells={(5, 5): 1},
            switches={
                (0, 0): Switch((0, 0), SwitchKind.SOFT, SwitchMode.PERMANENT_OPEN, (1,)),
                (0, 1): Switch((0, 1), SwitchKind.SOFT, SwitchMode.PERMANENT_CLOSE, (1,)),
            },
        )
        # Both switches pressed by one lying block: the later cell (close) wins.
        self.assertEqual(layout.apply_triggers([(0, 1), (0, 0)], 0, standing=False), 0)


class BridgeClosesUnderBlockTests(unittest.TestCase):
    def test_switch_closing_the_bridge_under_the_block_makes_it_fall(self) -> None:
        # Lying block lands on bridge (0,1) and switch (0,2); the toggle closes it.
        level = parse_grid(["S1o#G"], switches=[toggle((0, 2), 1)], initial_bridge_mask=1)
        self.assertIsNone(try_move(level, level.initial_state, Action.RIGHT))

    def test_same_move_is_legal_when_the_switch_keeps_the_bridge_open(self) -> None:
        keep_open = {"at": [0, 2], "mode": "permanent_open", "targets": [1]}
        level = parse_grid(["S1o#G"], switches=[keep_open], initial_bridge_mask=1)
        landed = try_move(level, level.initial_state, Action.RIGHT)
        self.assertIsNotNone(landed)
        self.assertEqual(landed.bridge_mask, 1)

    def test_switch_closing_a_bridge_elsewhere_is_harmless(self) -> None:
        level = parse_grid(
            ["S#o#G", "#####", "###1#"],
            switches=[toggle((0, 2), 1)],
            initial_bridge_mask=1,
        )
        landed = try_move(level, level.initial_state, Action.RIGHT)
        self.assertIsNotNone(landed)
        self.assertEqual(landed.bridge_mask, 0)

    def test_support_uses_the_mask_from_before_the_move(self) -> None:
        # The switch at (0,2) would open the bridge at (0,3) but the roll
        # onto it is judged under the old (closed) mask first.
        level = parse_grid(["S#o1G"], switches=[toggle((0, 2), 1)])
        lying = try_move(level, level.initial_state, Action.RIGHT)  # presses o
        self.assertEqual(lying.bridge_mask, 1)
        # Roll onto bridge cells: standing at (0,3) is supported by the new mask.
        self.assertIsNotNone(try_move(level, lying, Action.RIGHT))


class TileLayoutModelTests(unittest.TestCase):
    def test_empty_layout_is_empty_and_hashable(self) -> None:
        self.assertTrue(EMPTY_LAYOUT.is_empty)
        self.assertEqual(hash(EMPTY_LAYOUT), hash(TileLayout()))

    def test_levels_without_advanced_tiles_use_the_empty_layout(self) -> None:
        self.assertTrue(parse_grid(["S##G"]).tiles.is_empty)

    def test_layout_mappings_are_read_only(self) -> None:
        layout = TileLayout(bridge_cells={(0, 1): 1})
        with self.assertRaises(TypeError):
            layout.bridge_cells[(0, 2)] = 1  # type: ignore[index]

    def test_switch_must_target_an_existing_bridge(self) -> None:
        layout = TileLayout(
            switches={(0, 1): Switch((0, 1), SwitchKind.SOFT, SwitchMode.TOGGLE, (3,))}
        )
        with self.assertRaisesRegex(ValueError, "no cells"):
            layout.validate(frozenset({(0, 0), (0, 1), (0, 2)}), (0, 0), (0, 2))


if __name__ == "__main__":
    unittest.main()
