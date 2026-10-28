"""Tests for TV3 split-block movement, switch triggering, and merge mechanics."""

from __future__ import annotations

import unittest

from engine.core import (
    Action,
    GameState,
    IllegalMoveError,
    Level,
    Orientation,
    Position,
    apply_action,
    get_successors,
    is_goal,
    replay,
    try_move,
)
from engine.tiles import Switch, SwitchKind, SwitchMode, TileLayout, bridge_bit
from engine.split import (
    check_merge,
    check_split_switch_trigger,
    get_split_successors,
    try_move_split,
)
from solvers.bfs import solve as solve_bfs
from solvers.ucs import solve as solve_ucs, unit_cost_function


class SplitMechanicsTests(unittest.TestCase):
    def setUp(self) -> None:
        # 5x8 grid with a split switch at (0, 3) targeting (2, 0) and (2, 4)
        tiles: set[Position] = set()
        for r in range(5):
            for c in range(8):
                tiles.add((r, c))

        self.level = Level(
            name="Split Playground",
            width=8,
            height=5,
            floor_tiles=frozenset(tiles),
            start=(0, 0),
            goal=(2, 7),
            split_switches=(( (0, 3), ((2, 0), (2, 4)) ),),
        )

    def test_standing_on_split_switch_triggers_teleportation(self) -> None:
        # Start at (0, 0), roll RIGHT -> (0, 1) horizontal, roll RIGHT -> (0, 3) standing
        s0 = self.level.initial_state
        s1 = apply_action(self.level, s0, Action.RIGHT)
        self.assertFalse(s1.is_split)
        self.assertIs(s1.orientation, Orientation.HORIZONTAL)

        # Second RIGHT lands standing on (0, 3), triggering the split switch
        s2 = apply_action(self.level, s1, Action.RIGHT)
        self.assertTrue(s2.is_split)
        self.assertEqual(s2.cube_positions, ((2, 0), (2, 4)))
        self.assertEqual(s2.active_cube, 0)

    def test_lying_across_split_switch_does_not_trigger(self) -> None:
        # Move block so it lies horizontally across (0, 3): anchor (0, 2)
        state_lying = GameState.standard((0, 2), Orientation.HORIZONTAL)
        res = check_split_switch_trigger(self.level, state_lying)
        self.assertFalse(res.is_split)
        self.assertEqual(res.position, (0, 2))

    def test_switching_active_cube(self) -> None:
        state = GameState.split(((2, 0), (2, 4)), active_cube=0)
        next_state = try_move_split(self.level, state, Action.SWITCH)
        self.assertIsNotNone(next_state)
        assert next_state is not None
        self.assertTrue(next_state.is_split)
        self.assertEqual(next_state.cube_positions, ((2, 0), (2, 4)))
        self.assertEqual(next_state.active_cube, 1)

        # Switch back to 0
        switched_back = try_move_split(self.level, next_state, Action.SWITCH)
        self.assertIsNotNone(switched_back)
        assert switched_back is not None
        self.assertEqual(switched_back.active_cube, 0)

    def test_cube_movement_and_bounds(self) -> None:
        state = GameState.split(((2, 0), (2, 4)), active_cube=0)
        # Move cube 0 DOWN -> (3, 0)
        s_down = try_move(self.level, state, Action.DOWN)
        self.assertIsNotNone(s_down)
        assert s_down is not None
        self.assertEqual(s_down.cube_positions, ((2, 4), (3, 0)) if (2, 4) < (3, 0) else ((3, 0), (2, 4)))

        # Moving off top edge (cube 0 at (0, 0)) should be illegal
        top_state = GameState.split(((0, 0), (2, 4)), active_cube=0)
        self.assertIsNone(try_move(self.level, top_state, Action.UP))

    def test_cubes_cannot_occupy_same_cell(self) -> None:
        state = GameState.split(((2, 0), (2, 2)), active_cube=0)
        # Moving cube 0 directly to (2, 1) merges them, but if we check merge:
        # If cube 0 attempts to step onto cube 1 directly
        # try_move_split checks `next_pos == other_pos`
        self.assertIsNone(try_move_split(self.level, GameState.split(((2, 1), (2, 2)), active_cube=0), Action.RIGHT))

    def test_merge_horizontal_adjacent(self) -> None:
        # Cube 0 at (2, 2), Cube 1 at (2, 4). Move cube 0 RIGHT to (2, 3) -> adjacent to (2, 4)
        state = GameState.split(((2, 2), (2, 4)), active_cube=0)
        merged = try_move(self.level, state, Action.RIGHT)
        self.assertIsNotNone(merged)
        assert merged is not None
        self.assertFalse(merged.is_split)
        self.assertIs(merged.orientation, Orientation.HORIZONTAL)
        self.assertEqual(merged.position, (2, 3))

    def test_merge_vertical_adjacent(self) -> None:
        # Cube 0 at (1, 4), Cube 1 at (3, 4). Move cube 0 DOWN to (2, 4) -> adjacent vertically to (3, 4)
        state = GameState.split(((1, 4), (3, 4)), active_cube=0)
        merged = try_move(self.level, state, Action.DOWN)
        self.assertIsNotNone(merged)
        assert merged is not None
        self.assertFalse(merged.is_split)
        self.assertIs(merged.orientation, Orientation.VERTICAL)
        self.assertEqual(merged.position, (2, 4))

    def test_split_state_cannot_win(self) -> None:
        # Cube standing on goal does not satisfy is_goal
        split_at_goal = GameState.split(((self.level.goal), (0, 0)), active_cube=0)
        self.assertFalse(is_goal(self.level, split_at_goal))

    def test_intact_block_cannot_take_switch_action(self) -> None:
        intact = self.level.initial_state
        self.assertIsNone(try_move(self.level, intact, Action.SWITCH))
        with self.assertRaises(IllegalMoveError):
            apply_action(self.level, intact, Action.SWITCH)

    def test_solve_split_level_end_to_end(self) -> None:
        """Verify BFS and UCS can find and replay a complete solution involving split and merge."""
        # Start at (0, 0), split at (0, 3) -> ((2, 0), (2, 2))
        # Move cube 0 RIGHT to (2, 1) -> merges with (2, 2) at (2, 1) horizontal
        # Roll RIGHT to (2, 3) standing, roll RIGHT to (2, 4) horizontal, roll RIGHT to (2, 6) standing = goal
        tiles = {
            (0, 0), (0, 1), (0, 2), (0, 3),
            (2, 0), (2, 1), (2, 2), (2, 3), (2, 4), (2, 5), (2, 6),
        }
        level = Level(
            name="Mini Split Test",
            width=7,
            height=3,
            floor_tiles=frozenset(tiles),
            start=(0, 0),
            goal=(2, 6),
            split_switches=(( (0, 3), ((2, 0), (2, 2)) ),),
        )

        ucs_res = solve_ucs(level)
        self.assertTrue(ucs_res.found)
        self.assertGreater(ucs_res.solution_length, 0)
        self.assertTrue(is_goal(level, ucs_res.states[-1]))

        # Check replay
        replayed = replay(level, level.initial_state, ucs_res.moves)
        self.assertEqual(replayed, ucs_res.states)

        # BFS should also solve it
        bfs_res = solve_bfs(level)
        self.assertTrue(bfs_res.found)
        self.assertEqual(replay(level, level.initial_state, bfs_res.moves), bfs_res.states)


class SplitTileInteractionTests(unittest.TestCase):
    """Split cubes together with bridges, soft/heavy switches and fragile tiles."""

    def setUp(self) -> None:
        # Row 0 is a corridor; (0, 3) and (0, 4) are bridge 1, (0, 6) is bridge 2.
        # Below it: a soft switch, a heavy switch, a permanent soft switch and fragile ice.
        #   col: 0 1 2 3 4 5 6 7
        #   r0:  # # # 1 1 # 2 #
        #   r1:  o x p F # # # #
        #   r2:  # # # # # # # #
        floor = {(r, c) for r in range(3) for c in range(8)} - {(0, 3), (0, 4), (0, 6)}
        self.level = Level(
            name="Split Tiles",
            width=8,
            height=3,
            floor_tiles=frozenset(floor),
            start=(2, 7),
            goal=(2, 6),
            tiles=TileLayout(
                fragile=frozenset({(1, 3)}),
                bridge_cells={(0, 3): 1, (0, 4): 1, (0, 6): 2},
                switches={
                    (1, 0): Switch((1, 0), SwitchKind.SOFT, SwitchMode.TOGGLE, (1,)),
                    (1, 1): Switch((1, 1), SwitchKind.HEAVY, SwitchMode.TOGGLE, (1,)),
                    (1, 2): Switch((1, 2), SwitchKind.SOFT, SwitchMode.PERMANENT_OPEN, (2,)),
                },
            ),
        )
        self.open_1 = bridge_bit(1)
        self.open_2 = bridge_bit(2)

    def move(self, cubes, action, active=0, mask=0):
        return try_move(self.level, GameState.split(cubes, active_cube=active, bridge_mask=mask), action)

    def test_cube_crosses_an_open_bridge(self) -> None:
        moved = self.move(((0, 2), (2, 7)), Action.RIGHT, mask=self.open_1)
        self.assertIsNotNone(moved)
        assert moved is not None
        self.assertIn((0, 3), moved.cube_positions)
        self.assertEqual(moved.bridge_mask, self.open_1)

    def test_cube_falls_into_a_closed_bridge(self) -> None:
        self.assertIsNone(self.move(((0, 2), (2, 7)), Action.RIGHT, mask=0))
        self.assertIsNone(self.move(((0, 5), (2, 7)), Action.RIGHT, mask=self.open_1))

    def test_cube_presses_soft_switch_and_toggles_again(self) -> None:
        pressed = self.move(((2, 0), (2, 7)), Action.UP)
        self.assertIsNotNone(pressed)
        assert pressed is not None
        self.assertEqual(pressed.bridge_mask, self.open_1)
        off = try_move(self.level, pressed, Action.DOWN)
        assert off is not None
        self.assertEqual(off.bridge_mask, self.open_1, "stepping off does not fire the switch")
        again = try_move(self.level, off, Action.UP)
        assert again is not None
        self.assertEqual(again.bridge_mask, 0, "pressing a toggle switch twice closes the bridge")

    def test_cube_is_too_light_for_a_heavy_switch(self) -> None:
        moved = self.move(((2, 1), (2, 7)), Action.UP)
        self.assertIsNotNone(moved)
        assert moved is not None
        self.assertEqual(moved.bridge_mask, 0)

    def test_permanent_switch_stays_open_after_a_second_press(self) -> None:
        first = self.move(((2, 2), (2, 7)), Action.UP)
        assert first is not None
        self.assertEqual(first.bridge_mask, self.open_2)
        second = try_move(self.level, try_move(self.level, first, Action.DOWN), Action.UP)
        assert second is not None
        self.assertEqual(second.bridge_mask, self.open_2)

    def test_soft_switch_closing_the_bridge_under_the_other_cube_is_illegal(self) -> None:
        # Cube 1 waits on bridge 1; cube 0 toggles bridge 1 shut under it.
        self.assertIsNone(self.move(((0, 3), (2, 0)), Action.UP, active=1, mask=self.open_1))

    def test_cube_may_rest_on_fragile_ice(self) -> None:
        moved = self.move(((2, 3), (2, 7)), Action.UP)
        self.assertIsNotNone(moved)
        assert moved is not None
        self.assertIn((1, 3), moved.cube_positions)

    def test_merge_keeps_the_mask_set_by_the_last_cube_move(self) -> None:
        # Cube 0 steps on the soft switch (1, 0) right next to cube 1 at (1, 1): merge + toggle.
        merged = self.move(((2, 0), (1, 1)), Action.UP)
        self.assertIsNotNone(merged)
        assert merged is not None
        self.assertFalse(merged.is_split)
        self.assertEqual((merged.position, merged.orientation), ((1, 0), Orientation.HORIZONTAL))
        self.assertEqual(merged.bridge_mask, self.open_1)

    def test_bridge_mask_separates_otherwise_equal_split_states(self) -> None:
        closed = GameState.split(((2, 0), (2, 7)), bridge_mask=0)
        opened = GameState.split(((2, 0), (2, 7)), bridge_mask=self.open_1)
        self.assertNotEqual(closed, opened)
        self.assertEqual(len({closed, opened}), 2)

    def test_split_successors_keep_bridges_consistent(self) -> None:
        state = GameState.split(((0, 2), (2, 0)), active_cube=1)
        for action, nxt, cost in get_split_successors(self.level, state):
            with self.subTest(action=action):
                self.assertEqual(cost, 1)
                for cell in nxt.cube_positions or ():
                    if cell in self.level.tiles.bridge_cells:
                        self.assertTrue(self.level.tiles.is_bridge_open(cell, nxt.bridge_mask))


class SplitUcsCostTests(unittest.TestCase):
    """UCS returns the least total cost under the published cost model on split stages."""

    def test_ucs_cost_is_minimal_on_the_split_stages(self) -> None:
        from itertools import product
        from engine.level_loader import load_level
        from pathlib import Path
        from solvers.ucs import default_cost_function

        stage = Path(__file__).resolve().parents[1] / "levels" / "split" / "01_split_intro.json"
        level = load_level(stage)
        result = solve_ucs(level)
        self.assertTrue(result.found)

        # Exhaustive check: no action sequence up to the BFS length + 2 reaches the goal cheaper.
        def cost_of(actions):
            state, total = level.initial_state, 0.0
            for action in actions:
                nxt = try_move(level, state, action)
                if nxt is None:
                    return None
                total += default_cost_function(level, state, action, nxt)
                state = nxt
            return total if is_goal(level, state) else None

        best = min(c for n in range(1, result.solution_length + 3)
                   for seq in product(tuple(Action), repeat=n)
                   if (c := cost_of(seq)) is not None)
        self.assertAlmostEqual(result.path_cost, best)
        self.assertAlmostEqual(cost_of(result.moves), result.path_cost)


if __name__ == "__main__":
    unittest.main()
