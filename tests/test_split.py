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


if __name__ == "__main__":
    unittest.main()
