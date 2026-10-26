# Bloxorz Solver

This repository currently contains the TV1 handoff (shared immutable state
model, standard block mechanics, JSON/text level loading, BFS, required search
metrics, core tests), the TV2 handoff (fragile tiles, bridges, soft/heavy
switches with toggle/permanent modes, DFS and IDS, advanced stages and tests)
and the TV5 handoff (3D Tkinter GUI: manual play, solver buttons, metrics and
solution replay). Split-block movement, UCS, A*, experiments, and final media
remain for their assigned team members; the GUI enables the UCS and A* buttons
by itself once `solvers/ucs.py` and `solvers/astar.py` are merged.

## Requirements

- Python 3.10 or newer
- Tkinter for the GUI (bundled with the python.org installers for Windows and
  macOS; on Ubuntu/Debian: `sudo apt install python3-tk`)
- No third-party packages

## Play (GUI)

```bash
python main.py                                    # opens levels/basic/01_horizontal_intro.json
python main.py levels/demo/08_showcase.json       # opens a specific stage
```

| Key | Action |
|---|---|
| Arrows or W A S D | Roll the block (move the selected cube after a split) |
| Space | Switch the controlled cube after a split |
| Z, Ctrl+Z or Backspace | Undo a move (including the one that made the block fall) |
| R / Enter | Restart the stage / next stage after a win |
| P | Play or pause the solution replay |
| Mouse drag, wheel, Q / E, V | Orbit, zoom, turn the camera 15°, reset the view |

The side panel holds New Game, Restart, Open..., the solver buttons (BFS, DFS,
IDS, UCS, A*), the metrics of the last search and the replay controls. Every
move, win check and replayed solution goes through the shared engine; the GUI
has no rules of its own. The stage list shows `levels/basic`, then
`levels/advanced`, `levels/split` (split switches), `levels/hard` (large
benchmark stages, 35-46 moves) and `levels/demo` (the stages used in the demo
video).
Details, the 3D assets and integration notes are in
[`docs/tv5_handoff.md`](docs/tv5_handoff.md).

## Run the tests

```bash
python -m unittest discover -s tests -v
```

The suite verifies every one of the 12 orientation-direction transitions,
state hashing, illegal moves, the goal test, both level formats, BFS behavior,
metrics, ten core level cases, every advanced tile and switch kind (at least a
valid and an invalid case each), the advanced level format, nine advanced
stages, and DFS/IDS correctness, optimality and termination. The GUI tests
check that every stage loads into the board view exactly as the engine sees it,
that every available solver's answer replays to the goal, that each 3D roll
lands on the engine's footprint and that the 3D assets match their generator
(`python tools/build_models.py`); tests that open a window are skipped when no
display is available.

## Run BFS

```bash
python -m solvers.bfs levels/basic/01_horizontal_intro.json
```

The command prints a JSON summary with `found`, `moves`, `search_time`,
`peak_memory`, `expanded_nodes`, `solution_length`, and `path_cost`.

## Run DFS / IDS

```bash
python -m solvers.dfs levels/advanced/07_advanced_mix.json --strategy dfs
python -m solvers.dfs levels/advanced/07_advanced_mix.json --strategy ids
```

Both print the same JSON summary as BFS. In code, `solvers.dfs.solve(level,
state, strategy="dfs" | "ids")` returns a `SolverResult`. DFS is complete but
not optimal; IDS returns a shortest solution for unit step costs.

## Core level format

JSON stages use a `grid` array and may provide a name and an initial bridge
mask reserved for later advanced mechanics:

```json
{
  "name": "Horizontal Introduction",
  "grid": ["S##G"],
  "initial_bridge_mask": 0
}
```

Plain `.txt` and `.level` files contain only the grid. The symbols are:

- `S`: standing start tile
- `G`: goal tile
- `#`: ordinary floor
- space, `.`, `-`, or `0`: void

Every level must contain exactly one start and one goal. Short text rows are
padded with void cells.

## Advanced tiles

Extra grid symbols: `F` fragile floor (a standing block collapses it), `1`-`9`
bridge cells (solid only while the matching bit of the bridge mask is set), `o`
soft switch (any part of the block presses it) and `x` heavy switch (standing
block only). Switch behavior is configured in JSON:

```json
{
  "grid": ["S#o11#G"],
  "switches": [{"at": [0, 2], "mode": "toggle", "targets": [1]}]
}
```

`mode` is `toggle`, `permanent_open` or `permanent_close`; `initial_bridge_mask`
chooses which bridges start open. Full rules and the trigger convention are in
[`docs/tv2_handoff.md`](docs/tv2_handoff.md).

## Shared API

```python
from engine import get_successors, is_goal, load_level
from solvers.bfs import solve

level = load_level("levels/basic/01_horizontal_intro.json")
result = solve(level, level.initial_state)
```

`get_successors(level, state)` returns `(action, next_state, cost)` tuples.
All rolls, including those that fire switches, currently cost 1. `GameState` is frozen and hashable, and
its equality includes the complete bridge mask plus the reserved split-state
fields.

Detailed integration notes and report-ready technical descriptions are in
[`docs/tv1_handoff.md`](docs/tv1_handoff.md) and
[`docs/tv2_handoff.md`](docs/tv2_handoff.md); a Vietnamese draft of the TV2
report section is in [`docs/tv2_report_section_vi.md`](docs/tv2_report_section_vi.md).
