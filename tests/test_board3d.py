"""3D board checks: assets load and match their generator, rolls agree with the engine."""
import sys
import time
import tkinter as tk
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import build_models  # noqa: E402
from gui import models, render3d  # noqa: E402
from gui.app import App, find_stages  # noqa: E402
from gui.backend import DIRECTIONS, SPLIT, action_key, load_backend, state_view  # noqa: E402
from gui.board_view import CANONICAL, PIECE_MODELS, TILE_MODELS  # noqa: E402
from tests.test_gui import split_stage  # noqa: E402

LEVELS = ROOT / "levels"
ALL_MODELS = (*TILE_MODELS.values(), "buggy", *PIECE_MODELS, "marker")


class AssetTest(unittest.TestCase):
    def test_files_match_generator(self):
        for name, text in build_models.build_all().items():
            with self.subTest(file=name):
                on_disk = (models.MODELS_DIR / name).read_text(encoding="utf-8")
                self.assertEqual(on_disk, text, "run `python tools/build_models.py`")

    def test_models_are_closed_convex_solids(self):
        for name in ALL_MODELS:
            model = models.get(name)
            with self.subTest(model=name):
                solid = [f for f in model.faces if not f.decal]
                self.assertGreaterEqual(len(solid), 4)
                for face in solid:   # every face points away from the middle of the solid
                    mid = tuple(sum(p[i] for p in face.points) / len(face.points) for i in range(3))
                    self.assertGreater(render3d.dot(face.normal, render3d.sub(mid, model.center)), 0)
                for face in model.faces:
                    self.assertTrue(all(0 <= c <= 1 for c in face.rgb))

    def test_tiles_and_block_have_expected_size(self):
        for name in TILE_MODELS.values():
            model = models.get(name)
            self.assertEqual((model.lo[:2], model.hi), ((0, 0), (1, 1, 0)), name)
        self.assertEqual(models.get("buggy").hi, (1, 1, 2))
        self.assertGreater(sum(f.decal for f in models.get("buggy").faces), 20)


class RollTest(unittest.TestCase):
    def test_rolls_land_on_the_engine_footprint(self):
        """Rolling the 3D block over an edge ends exactly where the engine puts it."""
        backend = load_backend()
        block = models.get("buggy")
        for path in find_stages(LEVELS):
            level = backend.load_level(str(path))
            start = backend.initial_state(level)
            seen, todo = {start}, [start]
            while todo:
                state = todo.pop()
                view = state_view(level, state)
                for action, nxt, _ in backend.get_successors(level, state):
                    if nxt not in seen:
                        seen.add(nxt)
                        todo.append(nxt)
                    after, key = state_view(level, nxt), action_key(action)
                    if SPLIT in (view.orientation, after.orientation) or key not in DIRECTIONS:
                        continue
                    pose = render3d.place(block, CANONICAL[view.orientation], view.cells)
                    end = render3d.rolled(block, pose, key)
                    with self.subTest(stage=path.stem, view=view, move=key):
                        self.assertEqual(sorted(render3d.footprint(block, end)), sorted(after.cells))


class BoardTest(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no display available: {exc}")
        self.root.withdraw()
        self.app = App(self.root, load_backend(), LEVELS)
        self.board = self.app.board

    def tearDown(self):
        self.app.close()

    def settle(self):
        self.root.update()
        while self.board.animating:
            time.sleep(0.005)
            self.root.update()

    def press(self, *keys):
        for key in keys:
            self.app.move(key)
            self.settle()

    def test_block_rotation_follows_the_rolls(self):
        self.app.load_stage(LEVELS / "basic" / "02_horizontal_long.json")
        self.press("RIGHT")                     # standing -> lying: the head now points east
        self.assertEqual(render3d.apply(self.board._rot, render3d.Z), (1.0, 0.0, 0.0))
        self.press("RIGHT")                     # lying -> standing on his head
        self.assertEqual(render3d.apply(self.board._rot, render3d.Z), (0.0, 0.0, -1.0))

    def test_thin_ice_breaks_and_comes_back_on_undo(self):
        self.app.load_stage(LEVELS / "demo" / "04_fragile.json")
        self.press("DOWN", "LEFT", "UP", "RIGHT", "DOWN", "RIGHT")
        self.assertEqual(self.app.game_over, "lose")
        self.assertEqual(len(self.board._broken), 1)
        self.app.undo()
        self.assertEqual(self.board._broken, set())

    def test_split_draws_two_pieces_and_a_marker(self):
        path = split_stage(self.app.backend)
        if path is None:
            self.skipTest("no split stage yet: the split engine (TV3) is not merged")
        self.app.load_stage(path)
        result = self.app.backend.solvers["BFS"](self.app.level, self.app.initial)
        for move in result.moves:               # play the solution until the block splits
            self.press(action_key(move))
            if self.board.view.orientation == SPLIT:
                break
        self.assertEqual(self.board.view.orientation, SPLIT)
        kinds = [p.kind for p in self.board._rest_pieces()]
        self.assertEqual(kinds, [*PIECE_MODELS, "marker"])

    def test_camera_turns_and_resets(self):
        self.app.load_stage(LEVELS / "demo" / "08_showcase.json")
        self.board.orbit(30)
        self.root.update()
        self.assertNotEqual(self.board.cam.yaw, -22.0)
        self.board.reset_view()
        self.assertEqual((self.board.cam.yaw, self.board.zoom), (-22.0, 1.0))


if __name__ == "__main__":
    unittest.main()
