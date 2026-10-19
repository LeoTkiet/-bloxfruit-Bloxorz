"""Tests for immutable state and the twelve standard roll transitions."""

from __future__ import annotations

import unittest

from engine.core import (
    Action,
    GameState,
    IllegalMoveError,
    Level,
    Orientation,
    UnsupportedStateError,
    apply_action,
    get_successors,
    is_goal,
    occupied_cells,
    roll,
    try_move,
)


class RollTransitionTests(unittest.TestCase):
    def assert_roll(
        self,
        orientation: Orientation,
        action: Action,
        expected_position: tuple[int, int],
        expected_orientation: Orientation,
    ) -> None:
        state = GameState.standard((5, 5), orientation, bridge_mask=3)
        actual = roll(state, action)
        self.assertEqual(actual.position, expected_position)
        self.assertIs(actual.orientation, expected_orientation)
        self.assertEqual(actual.bridge_mask, 3)

    def test_standing_up(self) -> None:
        self.assert_roll(Orientation.STANDING, Action.UP, (3, 5), Orientation.VERTICAL)

    def test_standing_down(self) -> None:
        self.assert_roll(Orientation.STANDING, Action.DOWN, (6, 5), Orientation.VERTICAL)

    def test_standing_left(self) -> None:
        self.assert_roll(Orientation.STANDING, Action.LEFT, (5, 3), Orientation.HORIZONTAL)

    def test_standing_right(self) -> None:
        self.assert_roll(Orientation.STANDING, Action.RIGHT, (5, 6), Orientation.HORIZONTAL)

    def test_horizontal_up(self) -> None:
        self.assert_roll(Orientation.HORIZONTAL, Action.UP, (4, 5), Orientation.HORIZONTAL)

    def test_horizontal_down(self) -> None:
        self.assert_roll(Orientation.HORIZONTAL, Action.DOWN, (6, 5), Orientation.HORIZONTAL)

    def test_horizontal_left(self) -> None:
        self.assert_roll(Orientation.HORIZONTAL, Action.LEFT, (5, 4), Orientation.STANDING)

    def test_horizontal_right(self) -> None:
        self.assert_roll(Orientation.HORIZONTAL, Action.RIGHT, (5, 7), Orientation.STANDING)

    def test_vertical_up(self) -> None:
        self.assert_roll(Orientation.VERTICAL, Action.UP, (4, 5), Orientation.STANDING)

    def test_vertical_down(self) -> None:
        self.assert_roll(Orientation.VERTICAL, Action.DOWN, (7, 5), Orientation.STANDING)

    def test_vertical_left(self) -> None:
        self.assert_roll(Orientation.VERTICAL, Action.LEFT, (5, 4), Orientation.VERTICAL)

    def test_vertical_right(self) -> None:
        self.assert_roll(Orientation.VERTICAL, Action.RIGHT, (5, 6), Orientation.VERTICAL)


class StateAndRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.level = Level(
            name="Core test board",
            width=4,
            height=4,
            floor_tiles=frozenset(
                (row, column)
                for row in range(4)
                for column in range(4)
                if (row, column) != (1, 2)
            ),
            start=(0, 0),
            goal=(3, 3),
        )

    def test_occupied_cells_follow_anchor_convention(self) -> None:
        self.assertEqual(
            occupied_cells(GameState.standard((2, 2), Orientation.STANDING)),
            ((2, 2),),
        )
        self.assertEqual(
            occupied_cells(GameState.standard((2, 2), Orientation.HORIZONTAL)),
            ((2, 2), (2, 3)),
        )
        self.assertEqual(
            occupied_cells(GameState.standard((2, 2), Orientation.VERTICAL)),
            ((2, 2), (3, 2)),
        )

    def test_state_hash_includes_bridge_configuration(self) -> None:
        closed = GameState.standard((1, 1), bridge_mask=0)
        opened = GameState.standard((1, 1), bridge_mask=1)
        self.assertNotEqual(closed, opened)
        self.assertEqual(len({closed, opened}), 2)

    def test_split_state_is_canonical_and_hashable(self) -> None:
        first = GameState.split(((3, 4), (1, 2)), active_cube=0, bridge_mask=5)
        equivalent = GameState.split(((1, 2), (3, 4)), active_cube=1, bridge_mask=5)
        self.assertEqual(first, equivalent)
        self.assertEqual(first.cube_positions, ((1, 2), (3, 4)))
        self.assertEqual(first.active_cube, 1)
        self.assertEqual(len({first, equivalent}), 1)

    def test_invalid_mixed_state_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GameState(
                position=(0, 0),
                orientation=Orientation.STANDING,
                cube_positions=((1, 1), (1, 2)),
                active_cube=0,
            )

    def test_negative_bridge_mask_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            GameState.standard((0, 0), bridge_mask=-1)

    def test_split_movement_is_left_for_the_split_module(self) -> None:
        state = GameState.split(((0, 0), (0, 1)))
        with self.assertRaises(UnsupportedStateError):
            roll(state, Action.RIGHT)

    def test_move_over_void_is_illegal(self) -> None:
        state = GameState.standard((1, 0), Orientation.STANDING)
        self.assertIsNone(try_move(self.level, state, Action.RIGHT))

    def test_move_outside_board_is_illegal(self) -> None:
        state = GameState.standard((0, 0), Orientation.STANDING)
        self.assertIsNone(try_move(self.level, state, Action.UP))
        with self.assertRaises(IllegalMoveError):
            apply_action(self.level, state, Action.UP)

    def test_goal_requires_standing_orientation(self) -> None:
        standing = GameState.standard((3, 3), Orientation.STANDING)
        horizontal = GameState.standard((3, 2), Orientation.HORIZONTAL)
        split = GameState.split(((3, 3), (3, 2)))
        self.assertTrue(is_goal(self.level, standing))
        self.assertFalse(is_goal(self.level, horizontal))
        self.assertFalse(is_goal(self.level, split))

    def test_successors_have_unit_cost_and_deterministic_order(self) -> None:
        state = GameState.standard((3, 0), Orientation.STANDING)
        successors = get_successors(self.level, state)
        self.assertEqual([item[0] for item in successors], [Action.UP, Action.RIGHT])
        self.assertTrue(all(cost == 1 for _action, _state, cost in successors))


if __name__ == "__main__":
    unittest.main()
