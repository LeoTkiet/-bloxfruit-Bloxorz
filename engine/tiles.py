"""Advanced tile mechanics: fragile floor, bridges, and soft/heavy switches.

This module is deliberately free of imports from ``engine.core`` so that the
core can embed a :class:`TileLayout` in :class:`~engine.core.Level` without a
circular dependency. Every function works on plain coordinates, which also
makes it reusable by the split-block module (TV3).

Rules implemented here
----------------------

Fragile tile (``F``)
    Supports a block that is lying down (horizontal or vertical) but collapses
    under a standing block. A standing block on a fragile tile is an illegal
    placement, exactly like standing on void.

Bridge (digits ``1``-``9``)
    Every bridge has an id ``n`` in ``1..9`` and is controlled by bit ``n - 1``
    of ``GameState.bridge_mask``. A bridge cell is solid when its bit is set
    (open) and void when the bit is clear (closed). Because the mask is part of
    the state, search visited sets never merge two different bridge
    configurations.

Soft switch (``o``)
    Activated when *any* occupied cell of the block lands on it.

Heavy switch (``x``)
    Activated only when the block lands *standing* on it.

Switch modes
    ``toggle``           flips every target bridge each time it fires;
    ``permanent_open``   opens the targets and never closes them again;
    ``permanent_close``  closes the targets and never reopens them.

Trigger convention (shared with TV3)
    A switch fires exactly once per move, evaluated on the *landing*
    placement after the roll. It never fires per frame or while the block
    stays still. This is well defined because a roll never keeps any
    previously occupied cell, so one placement cannot press the same switch
    on two consecutive moves. When a lying block covers two switches, they
    fire in row-major cell order; for conflicting open/close effects the later
    one wins.

Support check order
    A roll must land on cells that are supported under the bridge mask in
    force *before* the move. Triggers are then applied, and the landing
    placement is checked again under the *new* mask. If a switch closes a
    bridge under the block that just pressed it, the block falls and the move
    is illegal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import AbstractSet, Iterable, Mapping, TypeAlias


Position: TypeAlias = tuple[int, int]

MAX_BRIDGES = 9


class SwitchKind(str, Enum):
    """Which block placements are able to press a switch."""

    SOFT = "soft"
    HEAVY = "heavy"


class SwitchMode(str, Enum):
    """How a pressed switch changes its target bridges."""

    TOGGLE = "toggle"
    PERMANENT_OPEN = "permanent_open"
    PERMANENT_CLOSE = "permanent_close"


def bridge_bit(bridge_id: int) -> int:
    """Return the bridge-mask bit for a bridge id in ``1..MAX_BRIDGES``."""

    if not isinstance(bridge_id, int) or isinstance(bridge_id, bool):
        raise ValueError(f"bridge id must be an integer, got {bridge_id!r}")
    if not 1 <= bridge_id <= MAX_BRIDGES:
        raise ValueError(f"bridge id must be in 1..{MAX_BRIDGES}, got {bridge_id}")
    return 1 << (bridge_id - 1)


@dataclass(frozen=True, slots=True)
class Switch:
    """A switch tile together with the bridges it controls."""

    position: Position
    kind: SwitchKind
    mode: SwitchMode = SwitchMode.TOGGLE
    targets: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.targets:
            raise ValueError(f"switch at {self.position} must control at least one bridge")
        for bridge_id in self.targets:
            bridge_bit(bridge_id)  # validates the id
        object.__setattr__(self, "targets", tuple(sorted(set(self.targets))))

    @property
    def target_mask(self) -> int:
        """Bit mask covering every bridge this switch controls."""

        mask = 0
        for bridge_id in self.targets:
            mask |= bridge_bit(bridge_id)
        return mask

    def apply(self, bridge_mask: int) -> int:
        """Return the bridge mask after this switch fires once."""

        target_mask = self.target_mask
        if self.mode is SwitchMode.TOGGLE:
            return bridge_mask ^ target_mask
        if self.mode is SwitchMode.PERMANENT_OPEN:
            return bridge_mask | target_mask
        return bridge_mask & ~target_mask

    def is_pressed_by(self, *, standing: bool) -> bool:
        """Return whether a placement that covers this tile presses it.

        ``standing`` states whether the pressing piece is an upright block. A
        soft switch ignores it; a heavy switch needs it.
        """

        return self.kind is SwitchKind.SOFT or standing


def _freeze(mapping: Mapping) -> Mapping:
    return MappingProxyType(dict(mapping))


@dataclass(frozen=True, slots=True)
class TileLayout:
    """Immutable description of every advanced tile in a level.

    ``fragile`` and the switch positions are ordinary floor tiles in
    ``Level.floor_tiles``. Bridge cells are *not* part of ``floor_tiles``;
    they are supported only while their bit is set in the bridge mask.
    """

    fragile: frozenset[Position] = frozenset()
    bridge_cells: Mapping[Position, int] = field(default_factory=dict, hash=False)
    switches: Mapping[Position, Switch] = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fragile", frozenset(self.fragile))
        object.__setattr__(self, "bridge_cells", _freeze(self.bridge_cells))
        object.__setattr__(self, "switches", _freeze(self.switches))
        for position, bridge_id in self.bridge_cells.items():
            try:
                bridge_bit(bridge_id)
            except ValueError as error:
                raise ValueError(f"bridge cell {position}: {error}") from error
        for position, switch in self.switches.items():
            if switch.position != position:
                raise ValueError(f"switch keyed at {position} reports {switch.position}")

    @property
    def is_empty(self) -> bool:
        """Return whether the level uses no advanced tile at all."""

        return not (self.fragile or self.bridge_cells or self.switches)

    # ------------------------------------------------------------------ support

    def is_bridge_open(self, position: Position, bridge_mask: int) -> bool:
        """Return whether ``position`` is a bridge cell that is currently solid."""

        bridge_id = self.bridge_cells.get(position)
        return bridge_id is not None and bool(bridge_mask & bridge_bit(bridge_id))

    def is_cell_supported(
        self,
        position: Position,
        floor_tiles: AbstractSet[Position],
        bridge_mask: int,
    ) -> bool:
        """Return whether a cell can carry weight: floor, or an open bridge."""

        return position in floor_tiles or self.is_bridge_open(position, bridge_mask)

    def violates_fragile(self, cells: Iterable[Position], *, standing: bool) -> bool:
        """Return whether a placement stands on a fragile tile."""

        return standing and any(cell in self.fragile for cell in cells)

    # ----------------------------------------------------------------- triggers

    def apply_triggers(
        self,
        cells: Iterable[Position],
        bridge_mask: int,
        *,
        standing: bool,
    ) -> int:
        """Fire every switch pressed by a landing placement; return the new mask.

        ``cells`` are the occupied cells after the roll, ``standing`` whether
        the piece is an upright block. Each switch fires at most once.
        """

        for cell in sorted(set(cells)):
            switch = self.switches.get(cell)
            if switch is not None and switch.is_pressed_by(standing=standing):
                bridge_mask = switch.apply(bridge_mask)
        return bridge_mask

    # --------------------------------------------------------------- validation

    def validate(
        self,
        floor_tiles: AbstractSet[Position],
        start: Position,
        goal: Position,
    ) -> None:
        """Raise ``ValueError`` when the layout contradicts the level geometry."""

        for position in self.fragile:
            if position not in floor_tiles:
                raise ValueError(f"fragile tile {position} must be a floor tile")
        for position, bridge_id in self.bridge_cells.items():
            if position in floor_tiles:
                raise ValueError(f"bridge cell {position} cannot also be floor")
        for position in self.switches:
            if position not in floor_tiles:
                raise ValueError(f"switch {position} must be a floor tile")
            if position in self.fragile:
                raise ValueError(f"switch {position} cannot also be fragile")
        known_bridges = set(self.bridge_cells.values())
        for switch in self.switches.values():
            for bridge_id in switch.targets:
                if bridge_id not in known_bridges:
                    raise ValueError(
                        f"switch {switch.position} targets bridge {bridge_id}, "
                        "which has no cells"
                    )
        if start in self.fragile or goal in self.fragile:
            raise ValueError("start and goal cannot be fragile tiles")
        if start in self.switches or goal in self.switches:
            raise ValueError("start and goal cannot be switches")


EMPTY_LAYOUT = TileLayout()
