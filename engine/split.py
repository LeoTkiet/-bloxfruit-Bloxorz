"""Split-block movement, switch triggering, and merge mechanics."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .core import (
    Action,
    GameState,
    Level,
    Orientation,
    Position,
    Successor,
)

if TYPE_CHECKING:
    pass

SPLIT_ACTION_ORDER: tuple[Action, ...] = (
    Action.UP,
    Action.DOWN,
    Action.LEFT,
    Action.RIGHT,
    Action.SWITCH,
)


def check_merge(
    cube1: Position,
    cube2: Position,
    bridge_mask: int = 0,
) -> GameState | None:
    """Return a standard merged GameState if two cubes are adjacent, or None."""

    r1, c1 = cube1
    r2, c2 = cube2

    # Horizontally adjacent: same row, adjacent columns
    if r1 == r2 and abs(c1 - c2) == 1:
        anchor = (r1, min(c1, c2))
        return GameState.standard(
            position=anchor,
            orientation=Orientation.HORIZONTAL,
            bridge_mask=bridge_mask,
        )

    # Vertically adjacent: same column, adjacent rows
    if c1 == c2 and abs(r1 - r2) == 1:
        anchor = (min(r1, r2), c1)
        return GameState.standard(
            position=anchor,
            orientation=Orientation.VERTICAL,
            bridge_mask=bridge_mask,
        )

    return None


def check_split_switch_trigger(level: Level, state: GameState) -> GameState:
    """Trigger split switch teleportation if an intact block is standing on one."""

    if state.is_split or state.orientation is not Orientation.STANDING:
        return state

    if not state.position or not hasattr(level, "split_switches"):
        return state

    split_map = level.split_switch_map
    if state.position in split_map:
        targets = split_map[state.position]
        # Check if targets are immediately adjacent (rare edge case)
        merged = check_merge(targets[0], targets[1], bridge_mask=state.bridge_mask)
        if merged is not None:
            return merged
        return GameState.split(
            cube_positions=targets,
            active_cube=0,
            bridge_mask=state.bridge_mask,
        )

    return state


def try_move_split(level: Level, state: GameState, action: Action) -> GameState | None:
    """Apply a move or active cube switch to a split GameState.

    Returns the next GameState (split or merged), or None if the move is illegal.
    """

    if not state.is_split:
        return None

    if len(state.cube_positions) != 2 or state.active_cube not in (0, 1):
        return None

    active_idx = state.active_cube
    other_idx = 1 - active_idx

    # Switching active cube control (no block position change)
    if action is Action.SWITCH:
        return GameState.split(
            cube_positions=state.cube_positions,
            active_cube=other_idx,
            bridge_mask=state.bridge_mask,
        )

    # Move active cube by 1 step in the specified direction
    active_pos = state.cube_positions[active_idx]
    other_pos = state.cube_positions[other_idx]
    row, col = active_pos

    if action is Action.UP:
        next_pos = (row - 1, col)
    elif action is Action.DOWN:
        next_pos = (row + 1, col)
    elif action is Action.LEFT:
        next_pos = (row, col - 1)
    elif action is Action.RIGHT:
        next_pos = (row, col + 1)
    else:
        return None

    # Boundary and floor tile check
    if not level.contains(next_pos):
        return None
    if next_pos not in level.floor_tiles:
        return None

    # Cannot occupy the exact same cell
    if next_pos == other_pos:
        return None

    # Check if the cubes become adjacent and merge back into an intact block
    merged = check_merge(next_pos, other_pos, bridge_mask=state.bridge_mask)
    if merged is not None:
        return merged

    # Remain split
    if active_idx == 0:
        new_cube_positions = (next_pos, other_pos)
    else:
        new_cube_positions = (other_pos, next_pos)

    return GameState.split(
        cube_positions=new_cube_positions,
        active_cube=active_idx,
        bridge_mask=state.bridge_mask,
    )


def get_split_successors(level: Level, state: GameState) -> list[Successor]:
    """Generate all legal successors from a split state in deterministic order."""

    successors: list[Successor] = []
    for action in SPLIT_ACTION_ORDER:
        next_state = try_move_split(level, state, action)
        if next_state is not None:
            successors.append((action, next_state, 1))
    return successors
