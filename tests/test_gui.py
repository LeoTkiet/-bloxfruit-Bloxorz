"""GUI smoke tests: stages load, solver answers replay to the goal, keys drive the engine."""
import importlib
import sys
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui import backend as gui_backend  # noqa: E402
from gui.app import App, find_stages  # noqa: E402
from gui.backend import (BRIDGE, FLOOR, FRAGILE, GOAL, SOLVER_LABELS, SPLIT, SPLIT_SWITCH,  # noqa: E402
                         VOID, StateView, action_key, level_view, load_backend, state_view)

LEVELS = ROOT / "levels"
STAGES = find_stages(LEVELS)


def split_stage(backend):
    """A stage with a split switch, or None while the split engine (TV3) is not merged."""
    for path in STAGES:
        lview = level_view(backend.load_level(str(path)))
        if any(sw.kind == SPLIT_SWITCH for sw in lview.switches.values()):
            return path
    return None


class BackendTest(unittest.TestCase):
    def setUp(self):
        self.backend = load_backend()

    def test_every_solver_replays_to_goal(self):
        for path in STAGES:
            level = self.backend.load_level(str(path))
            start = self.backend.initial_state(level)
            for label in SOLVER_LABELS:
                solve = self.backend.solvers[label]
                if solve is None:
                    continue
                with self.subTest(stage=path.stem, solver=label):
                    trace = self.backend.trace_solution(level, start, solve(level, start), label)
                    self.assertEqual(trace.found, "unsolvable" not in path.stem)
                    if trace.found:
                        self.assertTrue(self.backend.is_goal(level, trace.states[-1]))
                        self.assertEqual(len(trace.states), len(trace.moves) + 1)

    def test_level_view_matches_engine_layout(self):
        for path in STAGES:
            level = self.backend.load_level(str(path))
            lview = level_view(level)
            layout = level.tiles
            with self.subTest(stage=path.stem):
                self.assertEqual((lview.rows, lview.cols), (level.height, level.width))
                self.assertEqual(lview.tile(level.goal), GOAL)
                self.assertEqual(lview.tile(level.start), FLOOR)
                self.assertEqual(set(lview.bridges), set(layout.bridge_cells))
                for r in range(level.height):
                    for c in range(level.width):
                        kind = lview.tile((r, c))
                        self.assertEqual(kind == VOID, (r, c) not in level.floor_tiles
                                         and (r, c) not in layout.bridge_cells)
                        self.assertEqual(kind == FRAGILE, (r, c) in layout.fragile)
                        self.assertEqual(kind == BRIDGE, (r, c) in layout.bridge_cells)
                for pos, switch in layout.switches.items():
                    cells = {cell for cell, bridge in layout.bridge_cells.items()
                             if bridge in switch.targets}
                    self.assertEqual(set(lview.switches[pos].bridges), cells)
                    self.assertEqual(lview.tile(pos), switch.kind.value)

    def test_state_view_tracks_bridges_and_orientation(self):
        level = self.backend.load_level(str(LEVELS / "demo" / "05_soft_switch_bridge.json"))
        start = self.backend.initial_state(level)
        self.assertEqual(state_view(level, start),
                         StateView("STANDING", (level.start,), 0, frozenset()))
        result = self.backend.solvers["BFS"](level, start)
        views = [state_view(level, s) for s in result.states]
        for view in views:
            self.assertEqual(len(view.cells), 1 if view.orientation == "STANDING" else 2)
        self.assertIn(frozenset(level.tiles.bridge_cells), {v.open_bridges for v in views})

    def test_dfs_and_ids_buttons_use_their_own_strategy(self):
        level = self.backend.load_level(str(LEVELS / "advanced" / "07_advanced_mix.json"))
        start = self.backend.initial_state(level)
        lengths = {label: self.backend.solvers[label](level, start).solution_length
                   for label in ("BFS", "DFS", "IDS")}
        self.assertEqual(lengths["IDS"], lengths["BFS"])     # IDS is optimal for unit costs
        self.assertGreater(lengths["DFS"], lengths["BFS"])   # this stage leads DFS astray

    def test_missing_or_broken_solver_only_disables_its_button(self):
        real_import = importlib.import_module

        def fake_import(name):
            if name == "solvers.ucs":
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)
            if name == "solvers.astar":
                raise ImportError("cannot import name 'ParentEntry' from 'solvers.common'")
            return real_import(name)

        with mock.patch.object(gui_backend.importlib, "import_module", side_effect=fake_import):
            backend = load_backend()
        self.assertIsNotNone(backend.solvers["BFS"])
        self.assertIsNone(backend.solvers["UCS"])
        self.assertIsNone(backend.solvers["A*"])
        self.assertEqual(backend.unavailable["UCS"], "not merged yet")
        self.assertIn("ParentEntry", backend.unavailable["A*"])


class AppTest(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no display available: {exc}")
        self.root.withdraw()
        self.app = App(self.root, load_backend(), LEVELS)

    def tearDown(self):
        self.app.close()

    def settle(self):
        """Run the Tk event loop until the current animation has finished."""
        self.root.update()
        while self.app.board.animating:
            time.sleep(0.005)
            self.root.update()

    def press(self, *keys):
        for key in keys:
            self.app.move(key)
            self.settle()

    def test_stages_are_listed_by_group(self):
        labels = list(self.app.stage_box["values"])
        self.assertEqual(labels[0], "basic/01_horizontal_intro")
        self.assertLess(labels.index("basic/10_unsolvable_gap"),
                        labels.index("advanced/01_fragile_corridor"))
        self.assertIn("demo/08_showcase", labels)

    def test_unavailable_solver_buttons_are_disabled(self):
        for label, btn in self.app.solver_btns.items():
            with self.subTest(solver=label):
                available = self.app.backend.solvers[label] is not None
                self.assertEqual(btn.instate(["disabled"]), not available)

    def test_manual_play_wins_straight_line(self):
        self.app.load_stage(LEVELS / "basic" / "02_horizontal_long.json")
        self.press("RIGHT", "RIGHT", "RIGHT", "RIGHT")
        self.assertEqual(self.app.game_over, "win")
        self.assertEqual(len(self.app.history), 4)

    def test_illegal_move_loses_and_undo_recovers(self):
        self.app.load_stage(LEVELS / "basic" / "02_horizontal_long.json")
        self.press("LEFT")
        self.assertEqual(self.app.game_over, "lose")
        self.assertEqual(self.app.state, self.app.initial)
        self.app.undo()
        self.assertIsNone(self.app.game_over)
        self.press("RIGHT")
        self.assertEqual(len(self.app.history), 1)

    def test_split_stage_played_by_keys(self):
        path = split_stage(self.app.backend)
        if path is None:
            self.skipTest("no split stage yet: the split engine (TV3) is not merged")
        self.app.load_stage(path)
        result = self.app.backend.solvers["BFS"](self.app.level, self.app.initial)
        self.assertTrue(any(state_view(self.app.level, s).orientation == SPLIT
                            for s in result.states))
        self.press(*[action_key(m) for m in result.moves])
        self.assertEqual(self.app.game_over, "win")

    def test_solver_result_fills_replay(self):
        self.app.load_stage(LEVELS / "demo" / "03_classic_stage1.json")
        result = self.app.backend.solvers["BFS"](self.app.level, self.app.initial)
        self.app.show_result("BFS", result)
        self.assertEqual(self.app.moves_list.size(), len(result.moves) + 1)
        self.assertEqual(self.app.replay_index, 0)
        self.app._replay_jump(-1)
        self.assertEqual(self.app.game_over, "win")
        self.app._replay_step(-1)
        self.settle()
        self.assertEqual(self.app.replay_index, len(result.moves) - 1)

    def test_unsolvable_stage_reports_no_solution(self):
        self.app.load_stage(LEVELS / "basic" / "10_unsolvable_gap.json")
        result = self.app.backend.solvers["BFS"](self.app.level, self.app.initial)
        self.app.show_result("BFS", result)
        self.assertFalse(self.app.trace.found)
        self.assertEqual(self.app.metric_vars["found"].get(), "No")

    def test_stage_description_comes_from_the_json_file(self):
        self.app.load_stage(LEVELS / "demo" / "04_fragile.json")
        self.assertIn("lie across", self.app.desc_label["text"])


if __name__ == "__main__":
    unittest.main()
