"""Load core Bloxorz levels from a compact text or JSON grid."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .core import Level, Position


class LevelFormatError(ValueError):
    """Raised when a level file does not follow the documented core schema."""


FLOOR_SYMBOL = "#"
START_SYMBOL = "S"
GOAL_SYMBOL = "G"
VOID_SYMBOLS = frozenset({" ", ".", "-", "0"})


def parse_grid(
    rows: Sequence[str],
    *,
    name: str = "Unnamed level",
    initial_bridge_mask: int = 0,
) -> Level:
    """Parse grid rows into a validated core level.

    ``#`` is floor, ``S`` is the standing start, and ``G`` is the goal.
    Spaces, periods, hyphens, and zeroes are void cells. Short rows are padded
    with void cells to keep text levels easy to read.
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
            elif symbol not in VOID_SYMBOLS:
                raise LevelFormatError(
                    f"unsupported tile symbol {symbol!r} at row {row_index}, "
                    f"column {column_index}"
                )

    if len(starts) != 1:
        raise LevelFormatError(f"expected exactly one start tile, found {len(starts)}")
    if len(goals) != 1:
        raise LevelFormatError(f"expected exactly one goal tile, found {len(goals)}")

    try:
        return Level(
            name=name,
            width=width,
            height=len(rows),
            floor_tiles=frozenset(floor_tiles),
            start=starts[0],
            goal=goals[0],
            initial_bridge_mask=initial_bridge_mask,
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

    return parse_grid(
        rows,
        name=name,
        initial_bridge_mask=data.get("initial_bridge_mask", 0),
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
