"""Load Bloxorz levels (core and advanced tiles) from a text or JSON grid."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .core import Level, Position
from .tiles import (
    MAX_BRIDGES,
    Switch,
    SwitchKind,
    SwitchMode,
    TileLayout,
)


class LevelFormatError(ValueError):
    """Raised when a level file does not follow the documented core schema."""


FLOOR_SYMBOL = "#"
START_SYMBOL = "S"
GOAL_SYMBOL = "G"
VOID_SYMBOLS = frozenset({" ", ".", "-", "0"})
FRAGILE_SYMBOL = "F"
SOFT_SWITCH_SYMBOL = "o"
HEAVY_SWITCH_SYMBOL = "x"
BRIDGE_SYMBOLS = frozenset("123456789"[:MAX_BRIDGES])
SWITCH_KIND_BY_SYMBOL = {
    SOFT_SWITCH_SYMBOL: SwitchKind.SOFT,
    HEAVY_SWITCH_SYMBOL: SwitchKind.HEAVY,
}


def _parse_position(value: Any, label: str) -> Position:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or not all(isinstance(item, int) and not isinstance(item, bool) for item in value)
    ):
        raise LevelFormatError(f"{label} must be a [row, column] pair of integers")
    return (value[0], value[1])


def _build_switches(
    kinds: Mapping[Position, SwitchKind],
    configs: Sequence[Mapping[str, Any]],
) -> dict[Position, Switch]:
    """Combine switch symbols from the grid with their JSON configuration."""

    switches: dict[Position, Switch] = {}
    for index, config in enumerate(configs):
        label = f"switches[{index}]"
        if not isinstance(config, Mapping):
            raise LevelFormatError(f"{label} must be an object")
        position = _parse_position(config.get("at"), f"{label}.at")
        if position not in kinds:
            raise LevelFormatError(f"{label} at {position} is not marked 'o' or 'x' in the grid")
        if position in switches:
            raise LevelFormatError(f"switch at {position} is configured more than once")

        declared_kind = config.get("kind")
        if declared_kind is not None and declared_kind != kinds[position].value:
            raise LevelFormatError(
                f"{label} declares kind {declared_kind!r} but the grid symbol "
                f"means {kinds[position].value!r}"
            )

        mode_text = config.get("mode", SwitchMode.TOGGLE.value)
        if mode_text == "permanent":
            mode_text = SwitchMode.PERMANENT_OPEN.value
        try:
            mode = SwitchMode(mode_text)
        except ValueError as error:
            raise LevelFormatError(f"{label} has unknown mode {mode_text!r}") from error

        targets = config.get("targets")
        if (
            not isinstance(targets, list)
            or not targets
            or not all(isinstance(item, int) and not isinstance(item, bool) for item in targets)
        ):
            raise LevelFormatError(f"{label}.targets must be a non-empty list of bridge ids")
        try:
            switches[position] = Switch(position, kinds[position], mode, tuple(targets))
        except ValueError as error:
            raise LevelFormatError(f"{label}: {error}") from error

    missing = sorted(set(kinds) - set(switches))
    if missing:
        raise LevelFormatError(f"switch symbol at {missing[0]} has no entry in 'switches'")
    return switches


def parse_grid(
    rows: Sequence[str],
    *,
    name: str = "Unnamed level",
    initial_bridge_mask: int = 0,
    switches: Sequence[Mapping[str, Any]] | None = None,
    split_switches: Sequence[Any] = (),
) -> Level:
    """Parse grid rows into a validated level.

    ``#`` is floor, ``S`` is the standing start, and ``G`` is the goal.
    Spaces, periods, hyphens, and zeroes are void cells. Short rows are padded
    with void cells to keep text levels easy to read.

    Advanced symbols: ``F`` fragile floor, ``1``-``9`` bridge cells of bridge
    ``n`` (controlled by bit ``n - 1`` of the bridge mask), ``o`` soft switch
    and ``x`` heavy switch. Every switch needs one entry in ``switches`` of the
    form ``{"at": [row, col], "mode": "toggle", "targets": [1, 2]}`` where
    ``mode`` is ``toggle``, ``permanent_open`` or ``permanent_close``.
    """

    if not rows:
        raise LevelFormatError("a level must contain at least one grid row")
    if not all(isinstance(row, str) for row in rows):
        raise LevelFormatError("every grid row must be a string")
    if not isinstance(initial_bridge_mask, int) or isinstance(initial_bridge_mask, bool):
        raise LevelFormatError("initial_bridge_mask must be an integer")
    if initial_bridge_mask < 0:
        raise LevelFormatError("initial_bridge_mask must be non-negative")

    width = max((len(row) for row in rows), default=0)
    if width == 0:
        raise LevelFormatError("a level grid cannot be empty")

    floor_tiles: set[Position] = set()
    fragile_tiles: set[Position] = set()
    bridge_cells: dict[Position, int] = {}
    switch_kinds: dict[Position, SwitchKind] = {}
    starts: list[Position] = []
    goals: list[Position] = []

    for row_index, row in enumerate(rows):
        for column_index, symbol in enumerate(row):
            position = (row_index, column_index)
            if symbol == FLOOR_SYMBOL:
                floor_tiles.add(position)
            elif symbol == START_SYMBOL:
                starts.append(position)
                floor_tiles.add(position)
            elif symbol == GOAL_SYMBOL:
                goals.append(position)
                floor_tiles.add(position)
            elif symbol == FRAGILE_SYMBOL:
                fragile_tiles.add(position)
                floor_tiles.add(position)
            elif symbol in SWITCH_KIND_BY_SYMBOL:
                switch_kinds[position] = SWITCH_KIND_BY_SYMBOL[symbol]
                floor_tiles.add(position)
            elif symbol in BRIDGE_SYMBOLS:
                bridge_cells[position] = int(symbol)
            elif symbol not in VOID_SYMBOLS:
                raise LevelFormatError(
                    f"unsupported tile symbol {symbol!r} at row {row_index}, "
                    f"column {column_index}"
                )

    if len(starts) != 1:
        raise LevelFormatError(f"expected exactly one start tile, found {len(starts)}")
    if len(goals) != 1:
        raise LevelFormatError(f"expected exactly one goal tile, found {len(goals)}")

    if switches is None:
        switches = []
    elif isinstance(switches, (str, bytes)) or not isinstance(switches, Sequence):
        raise LevelFormatError("switches must be a list of objects")

    try:
        layout = TileLayout(
            fragile=frozenset(fragile_tiles),
            bridge_cells=bridge_cells,
            switches=_build_switches(switch_kinds, switches),
        )
    except ValueError as error:
        raise LevelFormatError(str(error)) from error

    try:
        return Level(
            name=name,
            width=width,
            height=len(rows),
            floor_tiles=frozenset(floor_tiles),
            start=starts[0],
            goal=goals[0],
            initial_bridge_mask=initial_bridge_mask,
            tiles=layout,
            split_switches=tuple(split_switches),
        )
    except ValueError as error:
        raise LevelFormatError(str(error)) from error


def _load_json(path: Path) -> Level:
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise LevelFormatError(f"invalid JSON in {path}: {error.msg}") from error

    if not isinstance(data, dict):
        raise LevelFormatError("a JSON level must be an object")
    rows = data.get("grid")
    if not isinstance(rows, list):
        raise LevelFormatError("a JSON level must contain a grid array")

    name = data.get("name", path.stem)
    if not isinstance(name, str):
        raise LevelFormatError("level name must be a string")

    raw_split = data.get("split_switches", [])
    parsed_split: list[tuple[Position, tuple[Position, Position]]] = []
    if isinstance(raw_split, list):
        for item in raw_split:
            if isinstance(item, dict) and "position" in item and "targets" in item:
                pos = (int(item["position"][0]), int(item["position"][1]))
                t1 = (int(item["targets"][0][0]), int(item["targets"][0][1]))
                t2 = (int(item["targets"][1][0]), int(item["targets"][1][1]))
                parsed_split.append((pos, (t1, t2)))

    return parse_grid(
        rows,
        name=name,
        initial_bridge_mask=data.get("initial_bridge_mask", 0),
        switches=data.get("switches"),
        split_switches=parsed_split,
    )


def load_level(path: str | Path) -> Level:
    """Load a ``.json``, ``.txt``, or ``.level`` core stage."""

    level_path = Path(path)
    if not level_path.is_file():
        raise FileNotFoundError(level_path)

    suffix = level_path.suffix.lower()
    if suffix == ".json":
        return _load_json(level_path)
    if suffix in {".txt", ".level"}:
        rows = level_path.read_text(encoding="utf-8").splitlines()
        return parse_grid(rows, name=level_path.stem)
    raise LevelFormatError(f"unsupported level file extension: {suffix or '<none>'}")
