"""Single binding point between the GUI and the shared engine/solver API (AI_PP.md section 4).

The GUI never computes transitions itself: manual moves, win checks and replays all go
through the engine's `get_successors` / `is_goal`. Everything the board draws is read from
`engine.Level` / `engine.GameState` in `level_view` / `state_view`, so a change in the
engine's data model only needs edits here.
"""
from __future__ import annotations

import functools
import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import engine

Cell = tuple[int, int]

# Tile kinds understood by the board view.
VOID, FLOOR, GOAL, FRAGILE, BRIDGE = "void", "floor", "goal", "fragile", "bridge"
SOFT, HEAVY, SPLIT_SWITCH = "soft", "heavy", "split"
STANDING, HORIZONTAL, VERTICAL, SPLIT = "STANDING", "HORIZONTAL", "VERTICAL", "SPLIT"

DIRECTIONS = ("UP", "DOWN", "LEFT", "RIGHT")
SWITCH = "SWITCH"
# Button label -> (solver module, keyword arguments for its `solve`).
_SOLVERS = {
    "BFS": ("solvers.bfs", {}),
    "DFS": ("solvers.dfs", {"strategy": "dfs"}),
    "IDS": ("solvers.dfs", {"strategy": "ids"}),
    "UCS": ("solvers.ucs", {}),
    "A*": ("solvers.astar", {}),
}
SOLVER_LABELS = tuple(_SOLVERS)
_ACTION_ALIASES = {"U": "UP", "D": "DOWN", "L": "LEFT", "R": "RIGHT",
                   "SWAP": SWITCH, "SPACE": SWITCH, "TOGGLE": SWITCH, "SWITCH_CUBE": SWITCH}
# engine.SwitchMode value -> wording shown on hover.
_SWITCH_ACTIONS = {"toggle": "toggle", "permanent_open": "open", "permanent_close": "close"}


class InvalidSolution(Exception):
    """A solver returned moves that the engine does not accept."""


@dataclass(frozen=True)
class SwitchView:
    kind: str
    action: str
    bridges: tuple[Cell, ...]
    targets: tuple[Cell, ...]


@dataclass(frozen=True, eq=False)
class LevelView:
    name: str
    description: str
    tiles: tuple[tuple[str, ...], ...]
    start: Cell
    goal: Cell
    bridges: tuple[Cell, ...]
    switches: dict[Cell, SwitchView]

    @property
    def rows(self) -> int:
        return len(self.tiles)

    @property
    def cols(self) -> int:
        return len(self.tiles[0]) if self.tiles else 0

    def tile(self, cell: Cell) -> str:
        r, c = cell
        if 0 <= r < self.rows and 0 <= c < self.cols:
            return self.tiles[r][c]
        return VOID


@dataclass(frozen=True)
class StateView:
    orientation: str          # STANDING | HORIZONTAL | VERTICAL | SPLIT
    cells: tuple[Cell, ...]   # block cells, or the two cubes when split
    active: int               # controlled cube when split
    open_bridges: frozenset[Cell]


@dataclass
class Trace:
    """A solver result checked against the engine, ready for replay."""
    algorithm: str
    found: bool
    moves: list[str] = field(default_factory=list)
    states: list = field(default_factory=list)   # states[0] is the initial state
    metrics: dict[str, Any] = field(default_factory=dict)
    warning: str | None = None


def action_key(action) -> str:
    name = getattr(action, "name", action)
    key = str(name).strip().upper().replace(" ", "_")
    return _ACTION_ALIASES.get(key, key)


def action_label(action) -> str:
    return "Switch cube" if action_key(action) == SWITCH else action_key(action).title()


def _get(obj, name: str, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def stage_description(path: str | Path) -> str:
    """The optional "description" of a JSON stage; the engine's Level does not keep it."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    description = data.get("description", "") if isinstance(data, dict) else ""
    return description if isinstance(description, str) else ""


def level_view(level: engine.Level, description: str = "") -> LevelView:
    layout = level.tiles
    bridges = tuple(sorted(layout.bridge_cells))
    switches = {
        pos: SwitchView(sw.kind.value, _SWITCH_ACTIONS[sw.mode.value],
                        tuple(cell for cell in bridges if layout.bridge_cells[cell] in sw.targets),
                        ())
        for pos, sw in layout.switches.items()
    }
    # Split switches come from TV3's engine/split.py; levels without them have none.
    for pos, targets in getattr(level, "split_switches", ()):
        switches[tuple(pos)] = SwitchView(SPLIT_SWITCH, "split", (), tuple(map(tuple, targets)))

    def kind(cell: Cell) -> str:
        if cell in switches:
            return switches[cell].kind
        if cell == level.goal:
            return GOAL
        if cell in layout.fragile:
            return FRAGILE
        if cell in layout.bridge_cells:
            return BRIDGE
        return FLOOR if cell in level.floor_tiles else VOID

    tiles = tuple(tuple(kind((r, c)) for c in range(level.width)) for r in range(level.height))
    return LevelView(level.name, description, tiles, level.start, level.goal, bridges, switches)


def state_view(level: engine.Level, state: engine.GameState) -> StateView:
    layout = level.tiles
    open_bridges = frozenset(cell for cell in layout.bridge_cells
                             if layout.is_bridge_open(cell, state.bridge_mask))
    if state.is_split:
        return StateView(SPLIT, tuple(state.cube_positions), state.active_cube, open_bridges)
    return StateView(state.orientation.name, engine.occupied_cells(state), 0, open_bridges)


@dataclass
class Backend:
    load_level: Callable[[str], Any]
    initial_state: Callable[[Any], Any]
    get_successors: Callable[[Any, Any], list]
    is_goal: Callable[[Any, Any], bool]
    solvers: dict[str, Callable | None]
    unavailable: dict[str, str] = field(default_factory=dict)   # label -> why it is disabled

    def successor_for(self, level, state, key: str):
        """The (action, next_state, cost) triple for a GUI action key, or None if illegal."""
        for action, nxt, cost in self.get_successors(level, state):
            if action_key(action) == key:
                return action, nxt, cost
        return None

    def trace_solution(self, level, initial, result, algorithm: str) -> Trace:
        """Replay a solver's moves through the engine so the GUI only ever shows legal states."""
        found = bool(_get(result, "found", False))
        moves = list(_get(result, "moves", None) or []) if found else []
        states, costs = [initial], []
        for i, move in enumerate(moves, 1):
            step = self.successor_for(level, states[-1], action_key(move))
            if step is None:
                raise InvalidSolution(f"{algorithm}: move {i} ({move}) is illegal in the engine.")
            states.append(step[1])
            costs.append(step[2])
        if found and not self.is_goal(level, states[-1]):
            raise InvalidSolution(f"{algorithm}: the returned moves do not end on the goal.")

        warning = None
        reported = list(_get(result, "states", None) or [])
        if found and reported:
            if len(reported) == len(moves):
                reported = [initial] + reported
            if reported != states:
                warning = f"{algorithm}: reported states differ from the engine replay."
        metrics = {
            "solution_length": _get(result, "solution_length", len(moves) if found else None),
            "path_cost": _get(result, "path_cost", sum(costs) if found else None),
            "expanded_nodes": _get(result, "expanded_nodes"),
            "search_time": _get(result, "search_time"),
            "peak_memory": _get(result, "peak_memory"),
        }
        return Trace(algorithm, found, [action_label(m) for m in moves], states, metrics, warning)


def load_backend() -> Backend:
    solvers, unavailable = {}, {}
    for label, (name, options) in _SOLVERS.items():
        try:
            module = importlib.import_module(name)
        except Exception as exc:
            # A missing or broken teammate module disables its button, not the whole GUI.
            missing = isinstance(exc, ModuleNotFoundError) and exc.name == name
            solvers[label] = None
            unavailable[label] = "not merged yet" if missing else f"{type(exc).__name__}: {exc}"
            continue
        solvers[label] = functools.partial(module.solve, **options) if options else module.solve
    return Backend(engine.load_level, lambda level: level.initial_state, engine.get_successors,
                   engine.is_goal, solvers, unavailable)
