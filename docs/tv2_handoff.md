# TV2 Handoff: Advanced Tiles and DFS/IDS

## Delivered scope

- `engine/tiles.py`: fragile tiles, bridges, soft/heavy switches, and the
  toggle / permanent switch modes. It has no dependency on `engine.core`, so
  TV3 can reuse it for split cubes.
- `engine/core.py`: `Level` gained one optional field, `tiles: TileLayout`
  (default: empty layout). `is_state_supported` and `try_move` now apply the
  tile rules. The public API (`get_successors`, `is_goal`, `GameState`,
  `SolverResult`) is unchanged; all 38 TV1 tests still pass untouched.
- `engine/level_loader.py`: new grid symbols and a `switches` block.
- `solvers/dfs.py`: DFS and IDS behind `solve(level, initial_state,
  strategy="dfs" | "ids")`, plus `solve_dfs` and `solve_ids(max_depth=None)`.
- `levels/advanced/`: nine stages (seven solvable, two unsolvable) with
  `expected_bfs_length` metadata, in the same style as `levels/basic`.
- Tests: `test_tiles.py`, `test_advanced_loader.py`, `test_advanced_levels.py`,
  `test_dfs.py` (73 new tests; 111 in total).

## Level format additions

| Symbol | Meaning |
| --- | --- |
| `F` | Fragile floor: supports a lying block, collapses under a standing one |
| `1`-`9` | Cell of bridge *n*; solid only if bit *n-1* of the bridge mask is set |
| `o` | Soft switch (any covered cell presses it) |
| `x` | Heavy switch (only a standing block presses it) |

`0` stays void. Each `o`/`x` needs one entry in the JSON `switches` list:

```json
{
  "grid": ["S#o11#G"],
  "initial_bridge_mask": 0,
  "switches": [{"at": [0, 2], "mode": "toggle", "targets": [1]}]
}
```

`mode` is `toggle` (default), `permanent_open` (alias `permanent`) or
`permanent_close`. `initial_bridge_mask` sets which bridges start open
(bit 0 = bridge 1). A switch's `kind` is derived from its grid symbol; an
optional `"kind"` key must agree with it. Text files (`.txt`, `.level`) support
`F` and bridges but have no place for switch configuration, so stages with
switches must be JSON.

## Trigger convention (agreed contract with TV3)

1. A switch fires **once per move**, evaluated on the placement the block
   *lands* on. It never fires per frame or while the block rests. A roll never
   keeps a previously occupied cell, so one placement cannot press the same
   switch on two consecutive moves.
2. Soft: any occupied cell on the switch. Heavy: only `Orientation.STANDING`.
   For split cubes TV3 calls `TileLayout.apply_triggers(cells, mask,
   standing=False)`, which fires soft switches only and never heavy ones.
3. If one lying block covers two switches, they fire in row-major cell order;
   for conflicting open/close effects the later one wins.
4. Support is checked in two steps. The landing cells must be supported under
   the mask **before** the move; after the triggers fire they are checked again
   under the **new** mask. A switch that closes a bridge under the block that
   just pressed it makes the block fall, so that move is illegal.
5. `bridge_mask` is a field of `GameState`; equality, hashing and every solver
   visited set therefore include it automatically.

## DFS and IDS design

Both are written from scratch on the shared `get_successors` / `is_goal`.

**DFS** uses an explicit stack of successor iterators (no recursion, so there
is no recursion-limit risk; a test solves a 1400-move corridor). A global
`visited` set over the whole `GameState` prevents cycles. The current stack is
the path, so the solution needs no parent map. DFS is complete on this finite
space but not optimal.

**IDS** repeats a depth-limited DFS with limits 0, 1, 2, ... Inside one
iteration `best_depth[state]` records the shallowest depth at which a state
was reached, and a state is re-opened only when reached strictly shallower.
This removes cycles without making the search incomplete for the limit. With
unit costs the first limit that reaches a goal gives a shortest solution.
An iteration that never has a non-goal state exactly at its limit has seen
the entire reachable graph, so IDS returns "not found" on unsolvable levels.
`max_depth` is an optional safety cap.

Metrics follow the BFS definitions: `expanded_nodes` counts non-goal states
whose successors were generated (summed over all iterations for IDS), and
`search_time` / `peak_memory` wrap the whole search and path reconstruction.
`path_cost` sums the step costs returned by the engine. IDS minimizes the
*number of moves*, so it is cost-optimal only while every step costs 1; for
non-uniform costs TV3's UCS is the right tool.

## Sample results (expanded nodes / solution length)

| Level | BFS | DFS | IDS |
| --- | --- | --- | --- |
| 01 fragile corridor | 4 / 4 | 4 / 4 | 10 / 4 |
| 02 fragile band | 50 / 6 | 47 / 34 | 85 / 6 |
| 03 soft switch bridge | 6 / 4 | 6 / 4 | 13 / 4 |
| 04 heavy switch bridge | 79 / 10 | 26 / 23 | 299 / 10 |
| 05 toggle two bridges | 7 / 6 | 7 / 6 | 21 / 6 |
| 06 permanent return | 6 / 6 | 6 / 6 | 21 / 6 |
| 07 advanced mix | 106 / 13 | 111 / 81 | 262 / 13 |

(Each cell is `expanded / length`. Counts are deterministic because successors
are generated in the fixed order Up, Down, Left, Right.)

## Notes for the other members

- TV3: the split state still raises `UnsupportedStateError` in `roll`. When you
  add cube movement, build the candidate cells, call
  `level.tiles.is_cell_supported(cell, level.floor_tiles, mask)` per cell and
  `level.tiles.apply_triggers(cells, mask, standing=False)`. Whether a lone cube
  may stand on a fragile tile is your call (`is_state_supported` currently does
  not restrict split states).
- TV4: heuristics must treat a closed bridge as passable only after the right
  switch; use `h = 0` for advanced levels unless a bound is proven.
- TV5: render `level.tiles` (fragile, bridge cells open/closed from
  `state.bridge_mask`, switch kinds) and call the engine for every move.
