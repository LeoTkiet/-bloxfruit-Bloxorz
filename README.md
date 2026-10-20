# Bloxorz Solver

This repository currently contains the TV1 handoff (shared immutable state
model, standard block mechanics, JSON/text level loading, BFS, required search
metrics, core tests) and the TV2 handoff (fragile tiles, bridges, soft/heavy
switches with toggle/permanent modes, DFS and IDS, advanced stages and tests).
Split-block movement, UCS, A*, the GUI, experiments, and final media remain
intentionally unimplemented for their assigned team members.

## Requirements

- Python 3.10 or newer
- No third-party packages for the current TV1 and TV2 modules

## Run the tests

```bash
python -m unittest discover -s tests -v
```

The suite verifies every one of the 12 orientation-direction transitions,
state hashing, illegal moves, the goal test, both level formats, BFS behavior,
metrics, ten core level cases, every advanced tile and switch kind (at least a
valid and an invalid case each), the advanced level format, nine advanced
stages, and DFS/IDS correctness, optimality and termination.

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
