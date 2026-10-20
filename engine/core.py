"""Core state model and standard Bloxorz movement rules.

The anchor convention is deliberately simple and shared by every caller:

* a standing block is anchored at its only occupied cell;
* a horizontal block is anchored at its left occupied cell; and
* a vertical block is anchored at its top occupied cell.

Advanced tile effects (fragile floor, bridges, switches) live in
``engine.tiles`` and are applied inside :func:`try_move`; split-block movement
belongs to TV3. The immutable state already reserves their search-relevant data
so that every solver can use the complete state as a hash key.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Iterable, TypeAlias

from .tiles import EMPTY_LAYOUT, TileLayout


Position: TypeAlias = tuple[int, int]


class Orientation(str, Enum):
    """The three orientations of an intact 1 x 1 x 2 block."""

    STANDING = "standing"
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class Action(str, Enum):
    """A standard block roll."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


ACTION_ORDER: tuple[Action, ...] = (
    Action.UP,
    Action.DOWN,
    Action.LEFT,
    Action.RIGHT,
)


class IllegalMoveError(ValueError):
    """Raised when a requested roll leaves any block cell unsupported."""


class UnsupportedStateError(ValueError):
    """Raised when core-only movement receives a split-block state."""


@dataclass(frozen=True, slots=True)
class GameState:
    """An immutable and hashable description of all search-relevant state.

    Standard states use ``position`` and ``orientation``. Reserved split
    states use ``cube_positions`` and ``active_cube`` instead. The bridge mask
    is present in both modes because two otherwise identical placements with
    different bridge configurations must remain different search states.
    """

    position: Position | None
    orientation: Orientation | None
    bridge_mask: int = 0
    cube_positions: tuple[Position, ...] = ()
    active_cube: int | None = None

    def __post_init__(self) -> None:
        if self.bridge_mask < 0:
            raise ValueError("bridge_mask must be non-negative")

        has_standard_fields = self.position is not None or self.orientation is not None
        has_split_fields = bool(self.cube_positions) or self.active_cube is not None

        if has_standard_fields and has_split_fields:
            raise ValueError("standard and split state fields cannot be mixed")

        if has_standard_fields:
            if self.position is None or self.orientation is None:
                raise ValueError("standard states require both position and orientation")
            return

        if len(self.cube_positions) != 2 or self.active_cube not in (0, 1):
            raise ValueError("split states require two cubes and an active cube index")
        if self.cube_positions[0] == self.cube_positions[1]:
            raise ValueError("split cubes cannot occupy the same cell")

        if self.cube_positions[1] < self.cube_positions[0]:
            object.__setattr__(self, "cube_positions", tuple(reversed(self.cube_positions)))
            object.__setattr__(self, "active_cube", 1 - self.active_cube)

    @classmethod
    def standard(
        cls,
        position: Position,
        orientation: Orientation = Orientation.STANDING,
        bridge_mask: int = 0,
    ) -> GameState:
        """Construct an intact-block state."""

        return cls(position=position, orientation=orientation, bridge_mask=bridge_mask)

    @classmethod
    def split(
        cls,
        cube_positions: tuple[Position, Position],
        active_cube: int = 0,
        bridge_mask: int = 0,
    ) -> GameState:
        """Construct the reserved state representation for two unit cubes."""

        return cls(
            position=None,
            orientation=None,
            bridge_mask=bridge_mask,
            cube_positions=cube_positions,
            active_cube=active_cube,
        )

    @property
    def is_split(self) -> bool:
        """Return whether this state represents two independent cubes."""

        return bool(self.cube_positions)


@dataclass(frozen=True, slots=True)
class Level:
    """The immutable geometry required by the standard game rules."""

    name: str
    width: int
    height: int
    floor_tiles: frozenset[Position]
    start: Position
    goal: Position
    initial_bridge_mask: int = 0
    tiles: TileLayout = EMPTY_LAYOUT

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("level dimensions must be positive")
        if self.initial_bridge_mask < 0:
            raise ValueError("initial_bridge_mask must be non-negative")
        if not self.name.strip():
            raise ValueError("level name cannot be empty")
        for label, position in (("start", self.start), ("goal", self.goal)):
            if not self.contains(position):
                raise ValueError(f"{label} must be inside the board")
            if position not in self.floor_tiles:
                raise ValueError(f"{label} must be supported by a floor tile")
        for position in self.floor_tiles:
            if not self.contains(position):
                raise ValueError(f"floor tile {position} is outside the board")
        for position in (*self.tiles.bridge_cells, *self.tiles.switches):
            if not self.contains(position):
                raise ValueError(f"advanced tile {position} is outside the board")
        self.tiles.validate(self.floor_tiles, self.start, self.goal)

    def contains(self, position: Position) -> bool:
        """Return whether a coordinate lies inside the rectangular board."""

        row, column = position
        return 0 <= row < self.height and 0 <= column < self.width

    @property
    def initial_state(self) -> GameState:
        """Return the required standing start state."""

        return GameState.standard(
            self.start,
            Orientation.STANDING,
            bridge_mask=self.initial_bridge_mask,
        )


Successor: TypeAlias = tuple[Action, GameState, int]


def occupied_cells(state: GameState) -> tuple[Position, ...]:
    """Return every cell occupied by a standard block or reserved split state."""

    if state.is_split:
        return state.cube_positions

    if state.position is None or state.orientation is None:
        raise ValueError("state is missing its standard block fields")

    row, column = state.position
    if state.orientation is Orientation.STANDING:
        return ((row, column),)
    if state.orientation is Orientation.HORIZONTAL:
        return ((row, column), (row, column + 1))
    return ((row, column), (row + 1, column))


def roll(state: GameState, action: Action) -> GameState:
    """Apply one geometric roll without checking board support."""

    if state.is_split:
        raise UnsupportedStateError("split-block movement is not part of the core module")
    if state.position is None or state.orientation is None:
        raise ValueError("state is missing its standard block fields")

    row, column = state.position
    orientation = state.orientation

    if orientation is Orientation.STANDING:
        transitions = {
            Action.UP: ((row - 2, column), Orientation.VERTICAL),
            Action.DOWN: ((row + 1, column), Orientation.VERTICAL),
            Action.LEFT: ((row, column - 2), Orientation.HORIZONTAL),
            Action.RIGHT: ((row, column + 1), Orientation.HORIZONTAL),
        }
    elif orientation is Orientation.HORIZONTAL:
        transitions = {
            Action.UP: ((row - 1, column), Orientation.HORIZONTAL),
            Action.DOWN: ((row + 1, column), Orientation.HORIZONTAL),
            Action.LEFT: ((row, column - 1), Orientation.STANDING),
            Action.RIGHT: ((row, column + 2), Orientation.STANDING),
        }
    else:
        transitions = {
            Action.UP: ((row - 1, column), Orientation.STANDING),
            Action.DOWN: ((row + 2, column), Orientation.STANDING),
            Action.LEFT: ((row, column - 1), Orientation.VERTICAL),
            Action.RIGHT: ((row, column + 1), Orientation.VERTICAL),
        }

    next_position, next_orientation = transitions[action]
    return GameState.standard(
        next_position,
        next_orientation,
        bridge_mask=state.bridge_mask,
    )


def is_state_supported(level: Level, state: GameState) -> bool:
    """Return whether the placement is legal under the state's bridge mask.

    Every occupied cell must lie on the board and be a floor tile or an open
    bridge, and an upright block must not stand on a fragile tile. Reserved
    split states are not subject to the fragile rule (TV3 decides it).
    """

    cells = occupied_cells(state)
    if not all(
        level.contains(position)
        and level.tiles.is_cell_supported(position, level.floor_tiles, state.bridge_mask)
        for position in cells
    ):
        return False
    standing = state.orientation is Orientation.STANDING
    return not level.tiles.violates_fragile(cells, standing=standing)


def try_move(level: Level, state: GameState, action: Action) -> GameState | None:
    """Return the next state, or ``None`` when the roll is illegal.

    The pipeline is: geometric roll -> support/fragile check under the old
    bridge mask -> fire the switches pressed by the landing placement ->
    support check again under the new mask (a bridge closed beneath the block
    makes it fall). See :mod:`engine.tiles` for the exact trigger rules.
    """

    candidate = roll(state, action)
    if not is_state_supported(level, candidate):
        return None
    if level.tiles.is_empty:
        return candidate

    standing = candidate.orientation is Orientation.STANDING
    new_mask = level.tiles.apply_triggers(
        occupied_cells(candidate), candidate.bridge_mask, standing=standing
    )
    if new_mask == candidate.bridge_mask:
        return candidate
    candidate = replace(candidate, bridge_mask=new_mask)
    return candidate if is_state_supported(level, candidate) else None


def apply_action(level: Level, state: GameState, action: Action) -> GameState:
    """Apply a legal roll and raise a descriptive error for an illegal one."""

    next_state = try_move(level, state, action)
    if next_state is None:
        raise IllegalMoveError(f"{action.value} is illegal from {state}")
    return next_state


def is_goal(level: Level, state: GameState) -> bool:
    """Return whether the intact block is standing on the goal hole."""

    return (
        not state.is_split
        and state.orientation is Orientation.STANDING
        and state.position == level.goal
    )


def get_successors(level: Level, state: GameState) -> list[Successor]:
    """Return legal standard rolls in a deterministic order with unit costs."""

    successors: list[Successor] = []
    for action in ACTION_ORDER:
        next_state = try_move(level, state, action)
        if next_state is not None:
            successors.append((action, next_state, 1))
    return successors


def replay(
    level: Level,
    initial_state: GameState,
    actions: Iterable[Action],
) -> tuple[GameState, ...]:
    """Replay legal actions and return the complete state sequence."""

    states = [initial_state]
    current = initial_state
    for action in actions:
        current = apply_action(level, current, action)
        states.append(current)
    return tuple(states)
