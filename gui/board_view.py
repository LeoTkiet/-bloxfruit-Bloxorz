"""Board rendering: the stage in 3D (render3d.py on a Tkinter canvas) with Buggy as the block.

Only the look is decided here. Which move is legal and where Buggy ends up always comes from the
engine; the board turns the change between two states into motion: the block rolls over an edge
of its footprint, a split piece rolls on its own, a split throws the head and the legs onto
their targets. The engine's state only knows the footprint, so the board keeps the block's full
rotation itself (which way his face and hat point) and carries it from move to move.
"""
from __future__ import annotations

import math
import random
import time
import tkinter as tk
from dataclasses import dataclass, replace

from . import models, theme
from .backend import (BRIDGE, FLOOR, FRAGILE, GOAL, HEAVY, HORIZONTAL, SOFT, SPLIT,
                      SPLIT_SWITCH, STANDING, VERTICAL, VOID, Cell, LevelView, StateView)
from .render3d import (DIRECTIONS, IDENTITY, WATER_Z, X, Y, Z, Camera, Pose, apply, bounds,
                       compose, corners, draw_model, footprint, lerp, long_axis, orient, place,
                       roll_hinge, rolled, rotation, snapped, sub)

FRAME_MS = 15
AMBIENT_MS = 120                  # waves drift and the active-piece marker bobs at this pace
BRIDGE_MS = 320
IDLE_TINT = 0.62                  # the split piece that is not being controlled is darker
TILE_MODELS = {FLOOR: "floor", GOAL: "goal", FRAGILE: "fragile", BRIDGE: "bridge",
               SOFT: "soft_switch", HEAVY: "heavy_switch", SPLIT_SWITCH: "split_switch"}
PIECE_MODELS = ("buggy_head", "buggy_legs")       # Buggy's two halves after a Bara Bara split
EFFECTS = ("ring", "sparkle", "puff")
DEFAULT_YAW, DEFAULT_PITCH = -22.0, 52.0
CANONICAL = {STANDING: IDENTITY, HORIZONTAL: orient(X, Y), VERTICAL: orient((0.0, -1.0, 0.0), Z)}
AXIS_OF = {STANDING: 2, HORIZONTAL: 0, VERTICAL: 1}
_NEIGHBOURS = ((-1, 0), (1, 0), (0, -1), (0, 1))


def smooth(t: float) -> float:
    return t * t * (3 - 2 * t)


@dataclass(frozen=True)
class Piece:
    """One thing drawn over the board: a model by name, or an effect ("ring", "sparkle",
    "puff") centred at pose.pos."""
    kind: str
    pose: Pose = Pose()
    tint: float = 1.0
    clip: float | None = None     # hide everything below this height
    sunk: bool = False            # below the tile tops: drawn between the tiles, not over them
    size: float = 0.0             # effects only


def _centre(cells) -> tuple[float, float]:
    return (sum(c for _, c in cells) / len(cells) + 0.5, sum(r for r, _ in cells) / len(cells) + 0.5)


def _direction(start, end) -> str | None:
    """The way a footprint went, from the shift of its centre."""
    (x0, y0), (x1, y1) = _centre(start), _centre(end)
    dx, dy = x1 - x0, y1 - y0
    if abs(dy) > abs(dx):
        return "DOWN" if dy > 0 else "UP"
    if dx:
        return "RIGHT" if dx > 0 else "LEFT"
    return None


def _inside(x: float, y: float, flat: list[float]) -> bool:
    pts = list(zip(flat[::2], flat[1::2]))
    hit = False
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def _circle(cam: Camera, x: float, y: float, z: float, radius: float, n: int = 16) -> list[float]:
    return cam.flat([(x + radius * math.cos(2 * math.pi * i / n),
                      y + radius * math.sin(2 * math.pi * i / n), z) for i in range(n)])


class BoardView(tk.Canvas):
    def __init__(self, master, on_hover=None, **kw):
        super().__init__(master, background=theme.SEA, highlightthickness=0, takefocus=1, **kw)
        self.level: LevelView | None = None
        self.view: StateView | None = None
        self.on_hover = on_hover
        self.hover: Cell | None = None
        self.cam = Camera(DEFAULT_YAW, DEFAULT_PITCH)
        self.zoom = 1.0
        self._banner: tuple[str, str, str] | None = None
        self._override: list[Piece] | None = None   # pieces drawn instead of `view` (animations)
        self._anim_job = self._bridge_job = self._redraw_job = None
        self._rot = IDENTITY                   # the whole block's rotation
        self._piece_rots = [IDENTITY, IDENTITY]
        self._lift: dict[Cell, float] = {}     # bridges rising or sinking: height of their top
        self._broken: set[Cell] = set()        # thin ice that gave way under Buggy
        self._ground: list[tuple[float, str]] = []           # (depth, tag) far to near
        self._quads: dict[Cell, tuple[list[float], float]] = {}   # tile tops on screen, for hover
        self._sunk: list[tuple[str, float]] = []
        self._waves: list[tuple[float, float, float, bool]] = []
        self._phase = 0.0
        self._drag = None
        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _e: self._set_hover(None))
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", lambda _e: setattr(self, "_drag", None))
        self.bind("<Double-Button-1>", lambda _e: self.reset_view())
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", self._on_wheel)
        self.bind("<Button-5>", self._on_wheel)
        self.bind("<Destroy>", self._on_destroy, add="+")
        self._ambient_job = self.after(AMBIENT_MS, self._ambient)

    # ---- public API -------------------------------------------------------------------------
    @property
    def animating(self) -> bool:
        return self._anim_job is not None

    def show(self, level: LevelView, view: StateView) -> None:
        self.cancel_animation()
        self._stop_bridges()
        if level is not self.level:
            self._new_level(level)
        self._broken.clear()
        self.level, self.view, self._override = level, view, None
        self._sync_rotation(view)
        self.redraw()

    def set_banner(self, title: str, subtitle: str = "", kind: str = "info") -> None:
        self._banner = (title, subtitle, kind)
        self._draw_overlay()

    def clear_banner(self) -> None:
        self._banner = None
        self.delete("overlay")

    def cancel_animation(self) -> None:
        if self._anim_job is not None:
            self.after_cancel(self._anim_job)
            self._anim_job = None

    def reset_view(self) -> None:
        self.cam.yaw, self.cam.pitch, self.zoom = DEFAULT_YAW, DEFAULT_PITCH, 1.0
        self._schedule_redraw()

    def orbit(self, degrees: float) -> None:
        self.cam.yaw = max(-75.0, min(75.0, self.cam.yaw + degrees))
        self._schedule_redraw()

    def animate_to(self, view: StateView, duration: int = 240, done=None) -> None:
        old = self.view
        frame = None
        if old is not None and duration > 0:
            if old.orientation != SPLIT and view.orientation != SPLIT:
                frame = self._roll_frames(old, view)
            elif old.orientation == SPLIT and view.orientation == SPLIT:
                frame = self._piece_frames(old, view)
            elif old.orientation == SPLIT:
                frame, duration = self._merge_frames(old, view), max(420, int(duration * 1.6))
            else:
                frame, duration = self._split_frames(old, view), max(650, int(duration * 2.6))
        if frame is None:            # nothing moved (switching pieces) or not a plain roll
            self.show(self.level, view)
            if done:
                done()
            return
        self._run(frame, duration, view, done)

    def animate_fall(self, direction: str, done=None) -> None:
        """Buggy rolls off the edge (or through the thin ice) and sinks into the sea."""
        pieces = self._rest_pieces(markers=False)
        i = self.view.active if self.view.orientation == SPLIT else 0
        moving = pieces[i]
        others = pieces[:i] + pieces[i + 1:]
        model = models.get(moving.kind)
        landed = rolled(model, moving.pose, direction)
        cells = footprint(model, landed)
        ice = cells[0] if (moving.kind == "buggy" and len(cells) == 1
                           and self.level.tile(cells[0]) == FRAGILE) else None
        _, axis = roll_hinge(model, moving.pose, direction)
        lo, hi = bounds(model, landed)
        centre = tuple((a + b) / 2 for a, b in zip(lo, hi))
        dx, dy, _ = DIRECTIONS[direction]

        def frame(t):
            if t < 0.35:
                u = t / 0.35
                return others + [replace(moving, pose=rolled(model, moving.pose, direction,
                                                              90 * u * u))]
            if ice is not None and ice not in self._broken:   # the ice gives way
                self._broken.add(ice)
                self._draw_ground()
            u = (t - 0.35) / 0.65
            drop = 3.0 * u * u
            pose = landed.rotated(centre, axis, 70 * u).moved((dx * 0.25 * u, dy * 0.25 * u, -drop))
            out = others + [replace(moving, pose=pose, clip=WATER_Z, sunk=True)]
            if ice is not None:
                out.append(Piece("fragile", Pose(pos=(ice[1], ice[0], -0.9 * drop)),
                                 clip=WATER_Z, sunk=True))
            splash = (u - 0.4) / 0.6
            if splash > 0:
                out.append(Piece("ring", Pose(pos=(centre[0], centre[1], WATER_Z)),
                                 tint=1 - splash, sunk=True, size=0.3 + 0.9 * splash))
            return out
        self._run(frame, 900, None, done)

    def animate_sink(self, done=None) -> None:
        """Buggy drops into the treasure hole and leaves a sparkle."""
        pieces = self._rest_pieces(markers=False)
        r, c = self.level.goal

        def frame(t):
            if t < 0.6:
                drop = 2.1 * (t / 0.6) ** 2
                return [replace(p, pose=p.pose.moved((0, 0, -drop)), clip=0.0) for p in pieces]
            u = (t - 0.6) / 0.4
            return [Piece("sparkle", Pose(pos=(c + 0.5 + 0.34 * math.cos(a + u),
                                               r + 0.5 + 0.34 * math.sin(a + u), 0.2 + 1.2 * u)),
                          size=1 - u)
                    for a in (k * math.pi / 3 for k in range(6))]
        self._run(frame, 800, None, done)

    # ---- animations -------------------------------------------------------------------------
    def _roll_frames(self, old: StateView, new: StateView):
        d = _direction(old.cells, new.cells)
        if d is None:
            return None
        block = models.get("buggy")
        start = place(block, self._rot, old.cells)
        end = rolled(block, start, d)
        if sorted(footprint(block, end)) != sorted(new.cells):
            return None
        self._rot = snapped(end.rot)
        return lambda t: [Piece("buggy", rolled(block, start, d, 90 * smooth(t)))]

    def _piece_frames(self, old: StateView, new: StateView):
        moved = [i for i in (0, 1) if old.cells[i] != new.cells[i]]
        if len(moved) != 1:
            return None
        i = moved[0]
        d = _direction([old.cells[i]], [new.cells[i]])
        model = models.get(PIECE_MODELS[i])
        start = place(model, self._piece_rots[i], [old.cells[i]])
        end = rolled(model, start, d)
        if footprint(model, end) != [new.cells[i]]:
            return None
        self._piece_rots[i] = snapped(end.rot)
        other = 1 - i
        still = Piece(PIECE_MODELS[other],
                      place(models.get(PIECE_MODELS[other]), self._piece_rots[other],
                            [old.cells[other]]),
                      1.0 if other == new.active else IDLE_TINT)
        tint = 1.0 if i == new.active else IDLE_TINT

        def frame(t):
            pose = rolled(model, start, d, 90 * smooth(t))
            out = [still, Piece(PIECE_MODELS[i], pose, tint)]
            return out + [self._marker(model, pose if i == new.active else still.pose)]
        return frame

    def _merge_frames(self, old: StateView, new: StateView):
        i, other = old.active, 1 - old.active
        rest = [cell for cell in new.cells if cell != old.cells[other]]
        if len(rest) != 1 or len(new.cells) != 2:
            return None
        target = rest[0]
        d = _direction([old.cells[i]], [target])
        model = models.get(PIECE_MODELS[i])
        start = place(model, self._piece_rots[i], [old.cells[i]])
        if d is None or footprint(model, rolled(model, start, d)) != [target]:
            return None
        still = Piece(PIECE_MODELS[other], place(models.get(PIECE_MODELS[other]),
                                                 self._piece_rots[other], [old.cells[other]]),
                      IDLE_TINT)
        head, legs = (target, old.cells[other]) if i == 0 else (old.cells[other], target)
        self._rot = orient((head[1] - legs[1], head[0] - legs[0], 0.0),
                           Y if new.orientation == HORIZONTAL else Z)
        merged = Piece("buggy", place(models.get("buggy"), self._rot, new.cells))
        x, y = _centre(new.cells)

        def frame(t):
            if t < 0.7:
                return [still, Piece(PIECE_MODELS[i], rolled(model, start, d, 90 * smooth(t / 0.7)))]
            u = (t - 0.7) / 0.3
            return [merged, Piece("puff", Pose(pos=(x, y, 0.5)), tint=1 - u, size=0.7 + 0.6 * u)]
        return frame

    def _split_frames(self, old: StateView, new: StateView):
        """The block rolls onto the split switch, then its head and legs fly to the targets."""
        switch = next((pos for pos, sw in self.level.switches.items()
                       if sw.kind == SPLIT_SWITCH and set(sw.targets) == set(new.cells)), None)
        block = models.get("buggy")
        start = stand = place(block, self._rot, old.cells)
        d = _direction(old.cells, [switch]) if switch is not None else None
        if d is not None:
            stand = rolled(block, start, d)
            if footprint(block, stand) != [switch]:
                stand, d = start, None
        rot = snapped(stand.rot)
        halves = (stand.point((0.5, 0.5, 1.5)), stand.point((0.5, 0.5, 0.5)))
        targets = [(c + 0.5, r + 0.5, 0.5) for r, c in new.cells]
        self._piece_rots = [rot, rot]
        roll_end = 0.35 if d is not None else 0.0

        def frame(t):
            if t < roll_end:
                return [Piece("buggy", rolled(block, start, d, 90 * smooth(t / roll_end)))]
            u = (t - roll_end) / (1 - roll_end)
            out = []
            for i, (a, b) in enumerate(zip(halves, targets)):
                x, y, z = lerp(a, b, smooth(u))
                z += (1.0 + 0.3 * math.dist(a[:2], b[:2])) * 4 * u * (1 - u)
                turn = compose(rotation(Z, 360 * smooth(u)), rot)
                pose = Pose(turn, sub((x, y, z), apply(turn, (0.5, 0.5, 0.5))))
                out.append(Piece(PIECE_MODELS[i], pose, 1.0 if i == new.active else IDLE_TINT))
            if switch is not None and u < 0.4:
                out.append(Piece("puff", Pose(pos=(switch[1] + 0.5, switch[0] + 0.5, 0.8)),
                                 tint=1 - u / 0.4, size=0.5 + 2 * u))
            return out
        return frame

    def _run(self, frame_fn, duration: int, final: StateView | None, done) -> None:
        """Play frame_fn(t), t from 0 to 1 over `duration` ms of wall time."""
        self.cancel_animation()
        start = time.perf_counter()

        def step():
            t = min(1.0, (time.perf_counter() - start) * 1000 / duration)
            self._override = frame_fn(t)
            self._draw_bodies()
            if t < 1.0:
                self._anim_job = self.after(FRAME_MS, step)
                return
            self._anim_job = None
            if final is not None:       # a real move: settle on the new state (bridges may change)
                self._settle(final)
            if done:
                done()
        step()

    def _settle(self, view: StateView) -> None:
        before = self.view.open_bridges if self.view else frozenset()
        self.view, self._override = view, None
        self._sync_rotation(view)
        self.redraw()
        if before != view.open_bridges:
            self._animate_bridges(before, view.open_bridges)

    def _animate_bridges(self, before, after) -> None:
        """Opened bridges rise out of the sea, closed ones sink back into it."""
        self._stop_bridges()
        opened, closed = after - before, before - after
        start = time.perf_counter()

        def step():
            t = min(1.0, (time.perf_counter() - start) * 1000 / BRIDGE_MS)
            e = smooth(t)
            self._lift = {**{c: -0.75 * (1 - e) for c in opened}, **{c: -0.75 * e for c in closed}}
            if t < 1.0:
                self._bridge_job = self.after(FRAME_MS, step)
            else:
                self._lift, self._bridge_job = {}, None
            self._draw_ground()
        step()

    def _stop_bridges(self) -> None:
        if self._bridge_job is not None:
            self.after_cancel(self._bridge_job)
            self._bridge_job = None
        self._lift = {}

    # ---- pieces -----------------------------------------------------------------------------
    def _new_level(self, level: LevelView) -> None:
        self._rot, self._piece_rots = IDENTITY, [IDENTITY, IDENTITY]
        rng = random.Random(level.name)
        self._waves = []
        for _ in range((level.rows + 6) * (level.cols + 6) // 3):
            x, y = rng.uniform(-3, level.cols + 3), rng.uniform(-3, level.rows + 3)
            if level.tile((math.floor(y), math.floor(x))) in (VOID, BRIDGE):
                self._waves.append((x, y, rng.uniform(0, 2 * math.pi), rng.random() < 0.3))

    def _sync_rotation(self, view: StateView) -> None:
        """Keep the block's rotation if it fits the state, else stand it the default way."""
        if view.orientation != SPLIT and long_axis(self._rot) != AXIS_OF.get(view.orientation, 2):
            self._rot = CANONICAL.get(view.orientation, IDENTITY)

    def _rest_pieces(self, markers: bool = True) -> list[Piece]:
        view = self.view
        if view.orientation != SPLIT:
            return [Piece("buggy", place(models.get("buggy"), self._rot, view.cells))]
        out = [Piece(name, place(models.get(name), self._piece_rots[i], [cell]),
                     1.0 if i == view.active else IDLE_TINT)
               for i, (name, cell) in enumerate(zip(PIECE_MODELS, view.cells))]
        if markers:
            out.append(self._marker(models.get(PIECE_MODELS[view.active]), out[view.active].pose))
        return out

    def _marker(self, model, pose: Pose) -> Piece:
        lo, hi = bounds(model, pose)
        bob = 0.08 * math.sin(self._phase * 1.6)
        return Piece("marker", Pose(pos=((lo[0] + hi[0]) / 2 - 0.5, (lo[1] + hi[1]) / 2 - 0.5,
                                         hi[2] + 0.25 + bob)))

    # ---- drawing ----------------------------------------------------------------------------
    def redraw(self) -> None:
        self.delete("all")
        self._ground, self._quads, self._sunk = [], {}, []
        if self.level is None:
            self.create_text(self.winfo_width() / 2, self.winfo_height() / 2, text="No stage loaded",
                             fill=theme.BOARD_TEXT, font=theme.FONT_BOLD)
            return
        self._layout()
        self._draw_waves()
        self._draw_ground()
        self._draw_links()
        self._draw_bodies()
        self._draw_compass()
        self._draw_overlay()

    def _schedule_redraw(self) -> None:
        if self._redraw_job is None:
            self._redraw_job = self.after(16, self._scheduled_redraw)

    def _scheduled_redraw(self) -> None:
        self._redraw_job = None
        self.redraw()

    def _layout(self) -> None:
        """Aim the camera at the board and scale it to fill the canvas."""
        w, h = max(self.winfo_width(), 100), max(self.winfo_height(), 100)
        rows, cols = self.level.rows, self.level.cols
        self.cam.target = (cols / 2, rows / 2, 0.0)
        self.cam.distance = 1.6 * math.hypot(rows, cols) + 8
        self.cam.frame(w, h, corners((0, 0, WATER_Z), (cols, rows, 2.0)), self.zoom, margin=24)

    def _restack(self) -> None:
        """Sea, foam, tiles, hover outlines, Buggy, then the window furniture, bottom to top;
        anything sunk below the tile tops goes back between the tiles by depth."""
        for tag in ("ground", "foam", "waves"):
            self.tag_lower(tag)
        for tag in ("links", "body"):
            self.tag_raise(tag)
        for tag, depth in self._sunk:
            nearer = next((g for d, g in self._ground if d < depth), None)
            if nearer is not None and self.find_withtag(nearer):
                self.tag_lower(tag, nearer)
        for tag in ("compass", "overlay"):
            self.tag_raise(tag)

    def _draw_waves(self) -> None:
        self.delete("waves")
        for x, y, seed, light in self._waves:
            dx = 0.12 * math.sin(self._phase + seed)
            pts = [(x - 0.22 + dx, y, WATER_Z), (x + dx, y - 0.07, WATER_Z),
                   (x + 0.22 + dx, y, WATER_Z)]
            self.create_line(self.cam.flat(pts), fill=theme.WAVE_LIGHT if light else theme.WAVE,
                             width=2, smooth=True, tags=("waves",))
        self._restack()

    def _draw_ground(self) -> None:
        self.delete("ground", "foam")
        cam, level = self.cam, self.level
        opened = self.view.open_bridges if self.view else frozenset()
        tiles, depth_of = [], {}         # (cell, model or None for a closed bridge, height)
        for r, row in enumerate(level.tiles):
            for c, kind in enumerate(row):
                cell = (r, c)
                if kind == VOID or cell in self._broken:
                    continue
                if kind == BRIDGE and cell in self._lift:
                    tiles.append((cell, "bridge", self._lift[cell]))
                elif kind == BRIDGE and cell not in opened:
                    tiles.append((cell, None, 0.0))
                else:
                    tiles.append((cell, TILE_MODELS[kind], 0.0))
                    depth_of[cell] = models.get(TILE_MODELS[kind]).depth

        for (r, c), depth in depth_of.items():       # surf where an island meets the sea
            if depth < -WATER_Z - 1e-6:
                continue
            for dr, dc in _NEIGHBOURS:
                if (r + dr, c + dc) in depth_of:
                    continue
                if dr:
                    y = r + (1.06 if dr > 0 else -0.06)
                    pts = [(c - 0.04, y, WATER_Z), (c + 1.04, y, WATER_Z)]
                else:
                    x = c + (1.06 if dc > 0 else -0.06)
                    pts = [(x, r - 0.04, WATER_Z), (x, r + 1.04, WATER_Z)]
                self.create_line(cam.flat(pts), fill=theme.FOAM, width=2, tags=("foam",))

        def centre(item):
            (r, c), _, z = item
            return cam.depth((c + 0.5, r + 0.5, z - 0.2))

        self._ground = []
        for rank, item in enumerate(sorted(tiles, key=centre, reverse=True)):   # far to near
            (r, c), name, z = item
            tag = f"g{rank}"
            if name is None:
                quad = [(c + 0.06, r + 0.06, -0.02), (c + 0.94, r + 0.06, -0.02),
                        (c + 0.94, r + 0.94, -0.02), (c + 0.06, r + 0.94, -0.02)]
                self.create_polygon(cam.flat(quad), fill="", outline=theme.BRIDGE_GHOST,
                                    dash=(4, 3), width=2, tags=("ground", tag))
            else:
                model = models.get(name)
                skip = {(dc, dr, 0) for dr, dc in _NEIGHBOURS
                        if depth_of.get((r + dr, c + dc), -1.0) >= model.depth}
                draw_model(self, cam, model, Pose(pos=(c, r, z)), ("ground", tag),
                           clip=WATER_Z if z < 0 else None, skip=skip, style="tile")
            self._ground.append((centre(item), tag))

        self._quads = {}
        for r, row in enumerate(level.tiles):
            for c, kind in enumerate(row):
                if kind != VOID:
                    top = [(c, r, 0.0), (c + 1, r, 0.0), (c + 1, r + 1, 0.0), (c, r + 1, 0.0)]
                    self._quads[(r, c)] = (cam.flat(top), cam.depth((c + 0.5, r + 0.5, 0.0)))
        self._restack()

    def _draw_links(self) -> None:
        """While hovering a switch or bridge, outline everything it is linked to."""
        self.delete("links")
        if self.level is None or self.hover is None:
            return
        cells, targets = set(), ()
        switch = self.level.switches.get(self.hover)
        if switch is not None:
            cells = {self.hover, *switch.bridges}
            targets = switch.targets
        elif self.level.tile(self.hover) == BRIDGE:
            cells = {self.hover} | {pos for pos, sw in self.level.switches.items()
                                    if self.hover in sw.bridges}
        for cell in cells:
            if cell in self._quads:
                self.create_polygon(self._quads[cell][0], fill="", outline=theme.HIGHLIGHT,
                                    width=3, tags=("links",))
        for r, c in targets:
            inner = [(c + 0.25, r + 0.25, 0.01), (c + 0.75, r + 0.25, 0.01),
                     (c + 0.75, r + 0.75, 0.01), (c + 0.25, r + 0.75, 0.01)]
            self.create_polygon(self.cam.flat(inner), fill="", outline=theme.SPLIT_COLOR,
                                width=3, tags=("links",))
        self._restack()

    def _draw_bodies(self) -> None:
        self.delete("body")
        self._sunk = []
        if self.view is None or self.level is None:
            return
        cam = self.cam
        pieces = self._override if self._override is not None else self._rest_pieces()

        def depth(p: Piece) -> float:
            if p.kind in EFFECTS:
                return cam.depth(p.pose.pos)
            return cam.depth(p.pose.point(models.get(p.kind).center))

        solids = sorted((p for p in pieces if p.kind not in EFFECTS and p.kind != "marker"),
                        key=depth, reverse=True)
        ordered = solids + [p for p in pieces if p.kind == "marker"] + \
            [p for p in pieces if p.kind in EFFECTS]
        for n, p in enumerate(ordered):
            tags = ("body",)
            if p.sunk:
                tags = ("body", f"sunk{n}")
                self._sunk.append((tags[1], depth(p)))
            if p.kind in EFFECTS:
                self._draw_effect(p, tags)
            else:
                style = "tile" if p.kind in TILE_MODELS.values() else "ink"
                draw_model(self, cam, models.get(p.kind), p.pose, tags, p.tint, p.clip, style=style)
        self._restack()

    def _draw_effect(self, p: Piece, tags) -> None:
        if p.tint <= 0.05 or p.size <= 0:
            return
        x, y, z = p.pose.pos
        if p.kind == "sparkle":
            sx, sy, _ = self.cam.project(p.pose.pos)
            s = 0.2 * p.size * self.cam.unit
            k = 0.28 * s
            star = [sx, sy - s, sx + k, sy - k, sx + s, sy, sx + k, sy + k,
                    sx, sy + s, sx - k, sy + k, sx - s, sy, sx - k, sy - k]
            self.create_polygon(star, fill=theme.GOLD_LIGHT, outline=theme.GOLD, tags=tags)
        else:
            color = theme.FOAM if p.kind == "ring" else "white"
            self.create_polygon(_circle(self.cam, x, y, z, p.size), fill="", outline=color,
                                width=max(1, round(4 * p.tint)), tags=tags)

    def _draw_compass(self) -> None:
        """Which way the Up key rolls Buggy, since the camera can turn."""
        self.delete("compass")
        cx, cy, radius = 40, self.winfo_height() - 40, 26
        x, y, _ = self.cam.target
        (x0, y0, _), (x1, y1, _) = self.cam.project((x, y, 0)), self.cam.project((x, y - 1, 0))
        length = math.hypot(x1 - x0, y1 - y0) or 1
        dx, dy = (x1 - x0) / length, (y1 - y0) / length
        self.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=theme.PANEL,
                         outline=theme.BORDER, width=2, tags=("compass",))
        self.create_line(cx - 12 * dx, cy - 12 * dy, cx + 12 * dx, cy + 12 * dy, arrow="last",
                         arrowshape=(9, 11, 4), fill=theme.GOLD, width=3, tags=("compass",))
        self.create_text(cx, cy + radius + 9, text="Up", fill=theme.BOARD_TEXT,
                         font=theme.FONT_SMALL, tags=("compass",))
        self._restack()

    def _draw_overlay(self) -> None:
        """Messages in a GBA-style dialog box."""
        self.delete("overlay")
        if self._banner is None:
            return
        title, subtitle, kind = self._banner
        w, h = self.winfo_width(), self.winfo_height()
        p = 3
        bw, bh = min(w - 8 * p, 480), 96 if subtitle else 64
        x0, y0 = (w - bw) // 2, (h - bh) // 2
        x1, y1 = x0 + bw, y0 + bh
        for inset, color in ((0, theme.INK), (p, theme.BORDER), (3 * p, theme.BANNER_COLORS[kind])):
            self.create_rectangle(x0 + inset, y0 + inset, x1 - inset, y1 - inset, fill=color,
                                  outline="", tags=("overlay",))
        ty = y0 + (32 if subtitle else bh / 2)
        for dx, color in ((2, theme.INK), (0, "white")):   # text with a drop shadow
            self.create_text(w / 2 + dx, ty + dx, text=title, fill=color, font=theme.FONT_BANNER,
                             tags=("overlay",))
        if subtitle:
            self.create_text(w / 2, y0 + 66, text=subtitle, fill="white", font=theme.FONT,
                             width=bw - 10 * p, tags=("overlay",))

    # ---- ambient animation / mouse ----------------------------------------------------------
    def _ambient(self) -> None:
        self._ambient_job = self.after(AMBIENT_MS, self._ambient)
        if self.level is None:
            return
        self._phase += 0.35
        self._draw_waves()
        if self.view is not None and self.view.orientation == SPLIT and self._override is None:
            self._draw_bodies()

    def _on_destroy(self, event) -> None:
        if event.widget is self:
            for job in (self._anim_job, self._bridge_job, self._redraw_job, self._ambient_job):
                if job is not None:
                    self.after_cancel(job)
            self._anim_job = self._bridge_job = self._redraw_job = None

    def _on_press(self, event) -> None:
        self.focus_set()
        self._drag = (event.x, event.y, self.cam.yaw, self.cam.pitch, False)

    def _on_drag(self, event) -> None:
        """Drag to turn the camera around the board."""
        if self._drag is None:
            return
        x0, y0, yaw, pitch, moved = self._drag
        if not moved and abs(event.x - x0) + abs(event.y - y0) < 4:
            return
        self._drag = (x0, y0, yaw, pitch, True)
        self._set_hover(None)
        self.cam.yaw = max(-75.0, min(75.0, yaw - (event.x - x0) * 0.4))
        self.cam.pitch = max(22.0, min(88.0, pitch + (event.y - y0) * 0.3))
        self._schedule_redraw()

    def _on_wheel(self, event) -> None:
        closer = getattr(event, "delta", 0) > 0 or getattr(event, "num", 0) == 4
        self.zoom = max(0.5, min(3.0, self.zoom * (1.1 if closer else 1 / 1.1)))
        self._schedule_redraw()

    def _on_motion(self, event) -> None:
        if self.level is None:
            return
        best = None
        for cell, (flat, depth) in self._quads.items():
            if (best is None or depth < best[1]) and _inside(event.x, event.y, flat):
                best = (cell, depth)
        self._set_hover(best[0] if best else None)

    def _set_hover(self, cell: Cell | None) -> None:
        if cell == self.hover:
            return
        self.hover = cell
        self._draw_links()
        if self.on_hover:
            self.on_hover(cell)


class Legend(tk.Frame):
    """Every tile type and the block, drawn with the same 3D models as the board."""
    ITEMS = (("Sea (void)", "sea"), ("Floor", "floor"), ("Goal hole", "goal"),
             ("Fragile (ice)", "fragile"), ("Bridge (open)", "bridge"),
             ("Bridge (closed)", "closed"), ("Soft switch", "soft_switch"),
             ("Heavy switch", "heavy_switch"), ("Split switch", "split_switch"),
             ("Buggy (block)", "buggy"), ("Active piece", "active"))

    def __init__(self, master, columns: int = 6, size: int = 34):
        super().__init__(master, background=theme.BG)
        for i, (text, key) in enumerate(self.ITEMS):
            icon = tk.Canvas(self, width=size, height=size, highlightthickness=0,
                             background=theme.SEA if key in ("sea", "closed") else theme.BG)
            self._draw_icon(icon, key, size)
            row, col = divmod(i, columns)
            icon.grid(row=row, column=2 * col, padx=(10, 4), pady=2)
            tk.Label(self, text=text, background=theme.BG, foreground=theme.BOARD_TEXT,
                     font=theme.FONT_SMALL).grid(row=row, column=2 * col + 1, sticky="w")

    @staticmethod
    def _draw_icon(canvas: tk.Canvas, key: str, size: int) -> None:
        cam = Camera(yaw=-30.0, pitch=36.0, distance=7.0)
        if key == "sea":
            for y, color in ((0.35, theme.WAVE_LIGHT), (0.65, theme.WAVE)):
                canvas.create_line(size * 0.2, size * y, size * 0.5, size * (y - 0.08), size * 0.8,
                                   size * y, fill=color, width=2, smooth=True)
            return
        if key == "closed":
            cam.target = (0.5, 0.5, 0.0)
            cam.frame(size, size, corners((0, 0, -0.1), (1, 1, 0.1)), margin=6)
            quad = [(0.06, 0.06, 0), (0.94, 0.06, 0), (0.94, 0.94, 0), (0.06, 0.94, 0)]
            canvas.create_polygon(cam.flat(quad), fill="", outline=theme.BRIDGE_GHOST, dash=(4, 3),
                                  width=2)
            return
        if key == "active":
            items = [("buggy_head", Pose()), ("marker", Pose(pos=(0.0, 0.0, 1.2)))]
        else:
            items = [(key, Pose())]
        pts = [p for name, pose in items for p in corners(*bounds(models.get(name), pose))]
        cam.target = tuple((min(p[i] for p in pts) + max(p[i] for p in pts)) / 2 for i in range(3))
        cam.frame(size, size, pts, margin=3)
        for name, pose in items:
            draw_model(canvas, cam, models.get(name), pose, ("icon",),
                       style="tile" if name in TILE_MODELS.values() else "ink")
