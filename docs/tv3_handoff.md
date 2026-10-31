# TV3 Handoff: Split/Merge Mechanics and Uniform-Cost Search (UCS)

## Delivered Scope

TV3 owns the split-block mechanics (block splitting, individual unit-cube navigation, active cube switching, auto-merging) and the Uniform-Cost Search (UCS) algorithm.

- `engine/split.py`:
  - Split-block movement rules and boundary/collision checks (`try_move_split`).
  - Active cube toggle mechanism (`Action.SWITCH`).
  - Automatic block merging when two unit cubes become adjacent (`check_merge`).
  - Split switch trigger and teleportation (`check_split_switch_trigger`).
  - Deterministic split successor generator (`get_split_successors`, `SPLIT_ACTION_ORDER`).
- `engine/core.py`:
  - Extended `Action` enum with `Action.SWITCH = "switch"`.
  - Added `split_switches` and `split_switch_map` property to `Level` with board and floor support validation.
  - Hooked split movement, switch triggers, and successor generation seamlessly into `try_move`, `get_successors`, and `roll`.
  - Maintained `is_goal` invariant: goal is only satisfied by an intact standing block (a single unit cube cannot win).
- `engine/level_loader.py`:
  - Extended `parse_grid` and `_load_json` to parse JSON `"split_switches"` declarations.
- `engine/__init__.py`:
  - Exported all TV3 symbols (`SPLIT_ACTION_ORDER`, `check_merge`, `check_split_switch_trigger`, `get_split_successors`, `try_move_split`).
- `solvers/ucs.py`:
  - Independent Uniform-Cost Search implementation using a priority queue (`heapq`).
  - Supports both non-uniform cost functions and `--unit-cost`.
  - Stale entry relaxation and parent-pointer path reconstruction.
  - Strict tracking of the 4 required metrics (`search_time`, `peak_memory`, `expanded_nodes`, `solution_length`) plus `path_cost`.
  - CLI runner matching standard interface: `python -m solvers.ucs <level_file> [--unit-cost]`.
- Stage assets & Tests:
  - `levels/split/01_split_intro.json`: Benchmark stage featuring split switch teleportation, split navigation, and merge.
  - `levels/demo/07_split.json`: demo stage where one cube opens the bridge on a soft switch before the merge (BFS 18).
  - `tests/test_split.py`: 21 unit tests covering split teleportation, cube switching, movement, collisions, merge mechanics,
    cubes with bridges and soft/heavy/permanent switches and fragile tiles, and UCS optimality under the published cost model.
  - `tests/test_ucs.py`: 7 unit tests verifying correctness, optimality, BFS parity under unit cost, and non-uniform cost path selection.
  - Project-wide test suite passes completely (188/188 tests passing on 2026-10-28).

---

## Split and Merge Mechanics

### 1. State Representation
In `GameState` (introduced by TV1), split states use:
- `cube_positions`: Canonical sorted tuple of two coordinates `((r1, c1), (r2, c2))` with `cube_positions[0] <= cube_positions[1]`.
- `active_cube`: Index (`0` or `1`) denoting which cube receives directional inputs (`Up`, `Down`, `Left`, `Right`).
- `position = None` and `orientation = None`.
- `bridge_mask`: Carries the current bridge state across splits and merges.

### 2. Action Space & Successors
When `state.is_split` is true, the action order is:
```python
SPLIT_ACTION_ORDER = (
    Action.UP,
    Action.DOWN,
    Action.LEFT,
    Action.RIGHT,
    Action.SWITCH,
)
```
- `Action.SWITCH`: Swaps `active_cube = 1 - active_cube` without moving either cube (position remains unchanged).
- Directional actions: Move only the cube indexed by `active_cube` by 1 cell. The other cube remains stationary.
- Illegal moves (return `None`):
  - Stepping outside the board (`not level.contains(pos)`).
  - Stepping onto void or a closed bridge (`level.tiles.is_cell_supported` is false under the current `bridge_mask`).
  - Stepping onto the exact same cell as the other cube (`next_pos == other_pos`).
  - Pressing a soft switch that closes a bridge under either cube (that cube falls).

### 2b. Unit Cubes and Advanced Tiles
A unit cube is light. After each cube move, `try_move_split` applies the same trigger rule as TV2's
intact block, with `standing=False`:

| Tile | Unit cube |
|---|---|
| Floor, fragile (`F`) | Supported. Fragile only breaks under a standing intact block. |
| Bridge (`1`-`9`) | Supported only while its bit is set in `bridge_mask`. |
| Soft switch (`o`) | Fires once when the cube lands on it (`toggle`, `permanent_open`, `permanent_close`). |
| Heavy switch (`x`) | Ignored: only an intact standing block presses it. |
| Split switch | Ignored: only an intact standing block triggers it. |
| Goal | A cube on the goal does not win. |

If the switch closes a bridge under the moving cube or the waiting cube, the move is illegal, the
same rule as an intact block falling through a bridge it just closed. The new mask is carried into
the next split state, or into the merged block.

These two rules (cubes on open bridges, cubes pressing soft switches) were added on 2026-10-28;
before that, cubes treated every bridge as void and never pressed a switch.

### 3. Automatic Merging
After every unit-cube move, `check_merge(cube1, cube2)` checks whether the two cubes are orthogonally adjacent (Manhattan distance = 1):
- **Horizontal merge**: `r1 == r2` and `abs(c1 - c2) == 1` $\rightarrow$ merges into an intact horizontal block with anchor `(r1, min(c1, c2))`.
- **Vertical merge**: `c1 == c2` and `abs(r1 - r2) == 1` $\rightarrow$ merges into an intact vertical block with anchor `(min(r1, r2), c1)`.
- The merged state keeps the `bridge_mask` produced by the move that merged it (the moving cube may just have pressed a soft switch).

### 4. Split Switches (Teleportation)
- **Grid symbol / JSON declaration**: Declared under `"split_switches"` in JSON levels:
  ```json
  "split_switches": [
    {
      "position": [0, 3],
      "targets": [[2, 0], [2, 2]]
    }
  ]
  ```
- **Trigger rule**: Fires **only** when an intact block lands **standing** on the switch coordinate.
- **Effect**: Teleports the block into two separate $1 \times 1 \times 1$ cubes placed at the configured `targets`. The active cube defaults to index `0`.
- A lying block covering a split switch does **not** trigger it. A lone unit cube does **not** re-trigger a split switch.

---

## Uniform-Cost Search (UCS) Design

UCS is implemented from scratch in `solvers/ucs.py` using Python's `heapq`:

1. **Priority Queue Structure**:
   Elements in the heap are `(cost, tie_breaker_counter, state)` tuples:
   - `cost`: Cumulative path cost $g(n)$ from the initial state.
   - `tie_breaker_counter`: Monotonically increasing integer ensuring deterministic FIFO tie-breaking without comparing `GameState` objects directly.
   - `state`: Immutable `GameState`.

2. **Relaxation and Stale Entries**:
   - `best_cost[state]` tracks the minimum cost discovered to reach `state`.
   - When a state is popped from the heap, if its recorded `cost > best_cost[state]`, it is discarded as a stale entry.
   - When expanding node $u$ with action $a$ to successor $v$ of step cost $c$:
     If $g(u) + c < \text{best\_cost}[v]$, update `best_cost[v] = g(u) + c`, update `parent[v] = (u, a)`, and push $v$ into the priority queue.

3. **Cost Functions**:
   - **Default (Non-Uniform Cost)**:
     - Standard directional movement: `1.0`
     - Switching active cube (`Action.SWITCH`): `0.5` (mental focus change, no physical block shift)
     - Split switch trigger / teleportation: `1.5` (energy cost of dissociation)
     - Every other move, including unit-cube moves: `1.0`
     - A step that lands on a fragile tile: `3.0` more (`FRAGILE_SURCHARGE`, added 31/10), so that UCS can take a different route from BFS. A cube resting on ice while the other one moves pays nothing.
   - **Unit Cost (`--unit-cost`)**:
     - Every action has cost `1.0`. Under unit cost, UCS produces solutions of identical length to BFS across all 10 basic levels and 9 advanced levels.

---

## Workspace Integration & Conflict Resolution

During integration with TV2's advanced tiles and DFS/IDS PR, the following shared files were merged and reconciled:
1. `engine/__init__.py`: Combines exports of both `engine.tiles` (TV2) and `engine.split` (TV3).
2. `engine/core.py`:
   - `Level` houses both `tiles: TileLayout` and `split_switches`.
   - `try_move` pipeline handles both split movement (`try_move_split`), intact tile triggers (`apply_triggers`), and split switch teleportation (`check_split_switch_trigger`).
   - `get_successors` branches to `get_split_successors` when split.
3. `engine/level_loader.py`:
   - `parse_grid` and `_load_json` accept both `switches` (bridges) and `split_switches`.
4. Stage assets organization:
   - TV2's regression suite expects exactly 9 stages under `levels/advanced/`.
   - TV3's split levels are located under `levels/split/` (e.g., `levels/split/01_split_intro.json`).

---

## Verification and Test Coverage

To run the complete test suite:
```powershell
python -m unittest discover -s tests -p "test_*.py"
```
**Result** (2026-10-28): 188 tests ran successfully, 28 of them TV3's (split & merge: 21, UCS: 7). At handoff time the suite had 128 tests.

To execute UCS directly on sample levels:
```powershell
# Basic level
python -m solvers.ucs levels/basic/01_horizontal_intro.json

# Split intro level (default non-uniform cost)
python -m solvers.ucs levels/split/01_split_intro.json

# Split intro level (unit cost)
python -m solvers.ucs levels/split/01_split_intro.json --unit-cost
```

---

## Notes for the Other Members

- **TV4 (A*)**:
  - `GameState` is fully hashable and works as a dictionary key or set element for A*.
  - When designing split heuristics $h(n)$, compute Manhattan distance from each individual cube to the goal or to each other for merging.
  - When `state.is_split`, `get_successors(level, state)` returns split successors with cost `1.0` by default.
- **TV5 (GUI)**:
  - Check `state.is_split`:
    - If `False`: Render intact block using `state.position` and `state.orientation`.
    - If `True`: Render two $1 \times 1 \times 1$ cubes at `state.cube_positions[0]` and `state.cube_positions[1]`. Highlight the active cube corresponding to `state.active_cube`.
  - Cube order: `GameState` keeps `cube_positions` sorted so that equal states hash alike, so element `0`
    is not always the same physical cube after a move. The engine keeps this canonical order (it is part
    of the search state). The GUI keeps each piece in its slot with `gui.backend.keep_piece_order`: the
    cube that did not move keeps its slot, so Buggy's head and legs never swap on screen.
  - Key bindings: Support arrow keys for movement, and spacebar or tab for `Action.SWITCH`.
