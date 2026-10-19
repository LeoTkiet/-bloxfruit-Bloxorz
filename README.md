# Bloxorz Solver

This repository currently contains the TV1 handoff: the shared immutable state
model, standard block mechanics, JSON/text level loading, a breadth-first search
solver, required search metrics, and automated core tests. Advanced tiles,
split-block movement, DFS/IDS, UCS, A*, the 3D GUI, experiments, and final media
remain intentionally unimplemented for their assigned team members.

## Requirements

- Python 3.10 or newer
- No third-party packages for the current TV1 modules

## Run the tests

```bash
python -m unittest discover -s tests -v
```

The suite verifies every one of the 12 orientation-direction transitions,
state hashing, illegal moves, the goal test, both level formats, BFS behavior,
metrics, and ten reusable core level cases.

## Run BFS

```bash
python -m solvers.bfs levels/basic/01_horizontal_intro.json
```

The command prints a JSON summary with `found`, `moves`, `search_time`,
`peak_memory`, `expanded_nodes`, `solution_length`, and `path_cost`.

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

## Shared API

```python
from engine import get_successors, is_goal, load_level
from solvers.bfs import solve

level = load_level("levels/basic/01_horizontal_intro.json")
result = solve(level, level.initial_state)
```

`get_successors(level, state)` returns `(action, next_state, cost)` tuples.
All standard rolls currently cost 1. `GameState` is frozen and hashable, and
its equality includes the complete bridge mask plus the reserved split-state
fields.

Detailed integration notes and report-ready technical descriptions are in
[`docs/tv1_handoff.md`](docs/tv1_handoff.md).
