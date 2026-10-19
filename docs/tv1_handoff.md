# TV1 Architecture Core Mechanics and BFS Handoff

## Delivered scope

TV1 owns the shared architecture, intact-block mechanics, basic stage loader,
and BFS. The current handoff includes:

- an immutable and hashable `GameState`;
- a stable anchor convention for all three intact-block orientations;
- the complete 12-case orientation and direction transition table;
- boundary, void, illegal-move, and standing-only goal checks;
- JSON and text stage loading;
- the shared `get_successors(level, state)` and `is_goal(level, state)` API;
- breadth-first search with path reconstruction and all required metrics; and
- ten basic regression stages plus automated tests.

The repository deliberately does not implement advanced tile behavior,
split-block movement, DFS/IDS, UCS, A*, the GUI, experiment plots, or video
production. Those areas remain available to their assigned owners.

## State and level representation

Coordinates use zero-based `(row, column)` tuples. An intact block has one of
three orientations. The state's position is the only occupied cell when the
block is standing, the left cell when it is horizontal, and the top cell when
it is vertical.

`GameState` also contains a non-negative bridge bit mask. Consequently, two
states with the same placement but different bridge configurations are not
equal and cannot be incorrectly merged by a solver's visited set. The model
reserves a canonical pair of cube positions and an active-cube index for TV3;
TV1 does not implement the corresponding movement or merge rules.

`Level` stores its dimensions, supported core floor cells, start, goal, and
initial bridge mask. Advanced modules can extend the loader and support test
while preserving the public solver API.

## Transition model

The following table specifies the anchor after a roll from `(r, c)`.

| Current orientation | Up | Down | Left | Right |
| --- | --- | --- | --- | --- |
| Standing | Vertical `(r-2, c)` | Vertical `(r+1, c)` | Horizontal `(r, c-2)` | Horizontal `(r, c+1)` |
| Horizontal | Horizontal `(r-1, c)` | Horizontal `(r+1, c)` | Standing `(r, c-1)` | Standing `(r, c+2)` |
| Vertical | Standing `(r-1, c)` | Standing `(r+2, c)` | Vertical `(r, c-1)` | Vertical `(r, c+1)` |

The geometric transition is computed first. A move is legal only if every
resulting occupied cell lies inside the board and belongs to the supported
floor set. The goal test succeeds only for an intact standing block whose
anchor equals the goal coordinate.

## BFS design

BFS uses a FIFO queue and a dictionary that serves both as the visited set and
the parent map. States are marked visited when they enter the queue, which
prevents duplicate frontier entries. Each discovered state records its parent
and incoming action. When the first goal is dequeued, following these links
back to the start reconstructs the move sequence and full state path.

All core rolls cost 1. Therefore, BFS explores states in nondecreasing path
length and the first discovered goal path has the minimum number of moves.

```text
enqueue start
visited[start] = no parent

while queue is not empty:
    state = dequeue
    if state is a goal:
        reconstruct and return the path
    count state as expanded
    for each legal successor in Up, Down, Left, Right order:
        if successor is not visited:
            record its parent and action
            enqueue successor

return no solution
```

## Metric definitions

- `search_time`: elapsed wall-clock seconds around search and reconstruction.
- `peak_memory`: peak additional traced Python memory in bytes during the same
  region.
- `expanded_nodes`: non-goal states removed from the queue whose successors
  are generated.
- `solution_length`: number of returned actions; zero for a start-at-goal path
  and also zero when no solution exists, distinguished by `found`.
- `path_cost`: equal to solution length for unit-cost BFS; `None` if unsolved.

## Basic regression stages

The ten files under `levels/basic` are the TV1 contribution to the fixed test
set. They cover horizontal and vertical rolling, turns, orientation-sensitive
routes, a void detour, and an unsolvable gap. Their verified optimal BFS
lengths are stored as `expected_bfs_length` metadata. Later owners should add
advanced levels rather than changing these baseline cases.

## Integration contract

- UI and solvers call the engine; they must not duplicate movement rules.
- `get_successors(level, state)` returns `(action, next_state, cost)` tuples.
- `solve(level, initial_state)` returns `SolverResult`.
- Every field that changes future legal moves must participate in state
  equality and hashing.
- TV2 can add fragile, bridge, and soft/heavy switch effects inside the engine
  transition pipeline while keeping this API.
- TV3 can add split movement, active-cube switching, and merge rules using the
  reserved state representation.
- TV4 can reuse `SolverResult` for A* and the experiment runner.
- TV5 can replay `result.states` or `result.moves` without reimplementing game
  rules.
