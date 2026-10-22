"""A small flat-shaded 3D renderer on a Tkinter canvas (no third-party packages).

World axes match the map: x = column (east), y = row (south), z = up; a tile top is at z = 0.
Models are convex, so back-face culling alone orders the faces of one model; models are
drawn far to near (painter's algorithm), which is exact for the board's grid of boxes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache

from . import theme
from .models import Model

Vec = tuple[float, float, float]
Matrix = tuple[Vec, Vec, Vec]        # rows

X, Y, Z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
IDENTITY: Matrix = (X, Y, Z)
WATER_Z = -0.55                      # sea level; island tiles reach down to it
LIGHT = (-0.5, 0.6, 1.0)             # towards the sun: above, south-west
AMBIENT, DIFFUSE = 0.42, 0.62


# ---- vectors and rotations --------------------------------------------------------------------
def add(a: Vec, b: Vec) -> Vec:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def sub(a: Vec, b: Vec) -> Vec:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def mul(a: Vec, k: float) -> Vec:
    return a[0] * k, a[1] * k, a[2] * k


def dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec, b: Vec) -> Vec:
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def unit(a: Vec) -> Vec:
    return mul(a, 1 / math.sqrt(dot(a, a)))


def lerp(a: Vec, b: Vec, t: float) -> Vec:
    return add(a, mul(sub(b, a), t))


def apply(m: Matrix, v: Vec) -> Vec:
    return dot(m[0], v), dot(m[1], v), dot(m[2], v)


def compose(a: Matrix, b: Matrix) -> Matrix:
    """a @ b: rotate by b, then by a."""
    cols = list(zip(*b))
    return tuple(tuple(dot(row, col) for col in cols) for row in a)


def rotation(axis: Vec, degrees: float) -> Matrix:
    """Turn about `axis` (Rodrigues); rotation(cross(Z, d), 90) tips +z over onto d."""
    x, y, z = unit(axis)
    a = math.radians(degrees)
    c, s, k = math.cos(a), math.sin(a), 1 - math.cos(a)
    return ((c + x * x * k, x * y * k - z * s, x * z * k + y * s),
            (y * x * k + z * s, c + y * y * k, y * z * k - x * s),
            (z * x * k - y * s, z * y * k + x * s, c + z * z * k))


def snapped(m: Matrix) -> Matrix:
    """Round a rotation made of quarter turns back to exact -1/0/1 entries."""
    return tuple(tuple(float(round(v)) for v in row) for row in m)


def orient(head: Vec, face: Vec) -> Matrix:
    """The rotation that points a model's +z (Buggy's head) along `head` and +y along `face`."""
    side = cross(face, head)
    return tuple(zip(side, face, head))


def long_axis(m: Matrix) -> int:
    """Index (0 = x, 1 = y, 2 = z) of the world axis the model's +z lies along."""
    v = apply(m, Z)
    return max(range(3), key=lambda i: abs(v[i]))


# ---- placement --------------------------------------------------------------------------------
@dataclass(frozen=True)
class Pose:
    """world = rot @ local + pos."""
    rot: Matrix = IDENTITY
    pos: Vec = (0.0, 0.0, 0.0)

    def point(self, p: Vec) -> Vec:
        return add(apply(self.rot, p), self.pos)

    def turn(self, v: Vec) -> Vec:
        return apply(self.rot, v)

    def moved(self, offset: Vec) -> Pose:
        return Pose(self.rot, add(self.pos, offset))

    def rotated(self, pivot: Vec, axis: Vec, degrees: float) -> Pose:
        """This pose turned about the line through `pivot` along `axis`."""
        r = rotation(axis, degrees)
        return Pose(compose(r, self.rot), add(pivot, apply(r, sub(self.pos, pivot))))


def corners(lo: Vec, hi: Vec) -> list[Vec]:
    return [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]


def bounds(model: Model, pose: Pose) -> tuple[Vec, Vec]:
    pts = [pose.point(p) for p in corners(model.lo, model.hi)]
    return (tuple(min(p[i] for p in pts) for i in range(3)),
            tuple(max(p[i] for p in pts) for i in range(3)))


def place(model: Model, rot: Matrix, cells) -> Pose:
    """The pose with rotation `rot` that stands the model on `cells` (row, col)."""
    r0, c0 = min(r for r, _ in cells), min(c for _, c in cells)
    lo, _ = bounds(model, Pose(rot))
    return Pose(rot, (c0 - lo[0], r0 - lo[1], -lo[2]))


def footprint(model: Model, pose: Pose) -> list[tuple[int, int]]:
    """The cells (row, col) under a model resting on the board."""
    lo, hi = bounds(model, pose)
    return [(r, c) for r in range(round(lo[1]), round(hi[1]))
            for c in range(round(lo[0]), round(hi[0]))]


DIRECTIONS = {"UP": (0.0, -1.0, 0.0), "DOWN": (0.0, 1.0, 0.0),
              "LEFT": (-1.0, 0.0, 0.0), "RIGHT": (1.0, 0.0, 0.0)}


def roll_hinge(model: Model, pose: Pose, direction: str) -> tuple[Vec, Vec]:
    """Pivot point and axis for rolling a resting model over its bottom edge towards `direction`."""
    d = DIRECTIONS[direction]
    lo, hi = bounds(model, pose)
    edge = tuple(hi[i] if d[i] > 0 else lo[i] if d[i] < 0 else 0.0 for i in range(2))
    return (edge[0], edge[1], lo[2]), cross(Z, d)


def rolled(model: Model, pose: Pose, direction: str, degrees: float = 90.0) -> Pose:
    pivot, axis = roll_hinge(model, pose, direction)
    return pose.rotated(pivot, axis, degrees)


# ---- camera -----------------------------------------------------------------------------------
@dataclass
class Camera:
    """Orbits `target`: yaw 0 looks north from the south, pitch 90 looks straight down."""
    yaw: float = -22.0
    pitch: float = 52.0
    distance: float = 20.0
    target: Vec = (0.0, 0.0, 0.0)
    focal: float = 1.0
    ox: float = 0.0
    oy: float = 0.0
    eye: Vec = field(default=(0.0, 0.0, 1.0))
    _r: Vec = X
    _u: Vec = Z
    _f: Vec = Y

    def frame(self, width: float, height: float, points, zoom: float = 1.0,
              margin: float = 20.0) -> None:
        """Aim at the target and scale so every point in `points` fits the canvas."""
        yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
        offset = (math.sin(yaw) * math.cos(pitch), math.cos(yaw) * math.cos(pitch), math.sin(pitch))
        self.eye = add(self.target, mul(offset, self.distance))
        self._f = mul(offset, -1)
        self._r = unit((-self._f[1], self._f[0], 0.0))
        self._u = cross(self._f, self._r)
        self.focal, self.ox, self.oy = 1.0, 0.0, 0.0
        xs, ys = zip(*(self.project(p)[:2] for p in points))
        span_x, span_y = max(xs) - min(xs) or 1e-6, max(ys) - min(ys) or 1e-6
        self.focal = zoom * min(max(width - 2 * margin, 10) / span_x,
                                max(height - 2 * margin, 10) / span_y)
        self.ox = width / 2 - self.focal * (max(xs) + min(xs)) / 2
        self.oy = height / 2 - self.focal * (max(ys) + min(ys)) / 2

    def project(self, p: Vec) -> tuple[float, float, float]:
        """Screen x, y and depth (distance along the view direction) of a world point."""
        d = sub(p, self.eye)
        z = max(dot(d, self._f), 1e-3)
        return self.ox + self.focal * dot(d, self._r) / z, self.oy - self.focal * dot(d, self._u) / z, z

    def depth(self, p: Vec) -> float:
        return dot(sub(p, self.eye), self._f)

    def facing(self, normal: Vec, point: Vec) -> bool:
        return dot(normal, sub(self.eye, point)) > 1e-9

    @property
    def unit(self) -> float:
        """Roughly how many pixels one world unit spans at the target."""
        return self.focal / self.distance

    def flat(self, points) -> list[float]:
        out = []
        for p in points:
            x, y, _ = self.project(p)
            out += (x, y)
        return out


# ---- shading and drawing ----------------------------------------------------------------------
_LIGHT = unit(LIGHT)


@lru_cache(maxsize=8192)
def _hex(rgb, level: int) -> str:
    k = level / 64
    return "#%02x%02x%02x" % tuple(min(255, int(c * k * 255 + 0.5)) for c in rgb)


def shade(rgb, normal: Vec, tint: float = 1.0) -> str:
    light = AMBIENT + DIFFUSE * max(0.0, dot(normal, _LIGHT))
    return _hex(tuple(rgb), round(light * tint * 64))


def clip_below(points: list[Vec], z: float) -> list[Vec]:
    """Sutherland-Hodgman: the part of a polygon with height >= z."""
    out = []
    for a, b in zip(points, points[1:] + points[:1]):
        a_in, b_in = a[2] >= z, b[2] >= z
        if a_in:
            out.append(a)
        if a_in != b_in:
            out.append(lerp(a, b, (z - a[2]) / (b[2] - a[2])))
    return out


def draw_model(canvas, cam: Camera, model: Model, pose: Pose, tags, tint: float = 1.0,
               clip: float | None = None, skip=frozenset(), style: str = "plain") -> None:
    """Draw one model. style: "tile" outlines tops (shows the grid), "ink" outlines the solid in
    the window's ink colour (cartoon edges), "plain" draws no edges. `skip` holds world
    normals, rounded to integers, of faces hidden by neighbours."""
    ink_width = 2 if cam.unit > 40 else 1
    for face in model.faces:
        n = pose.turn(face.normal)
        if skip and (round(n[0]), round(n[1]), round(n[2])) in skip:
            continue
        pts = [pose.point(p) for p in face.points]
        if not cam.facing(n, pts[0]):
            continue
        if clip is not None:
            pts = clip_below(pts, clip)
            if len(pts) < 3:
                continue
        fill = shade(face.rgb, n, tint)
        outline, width = fill, 1
        if not face.decal:
            if style == "ink":
                outline, width = theme.INK, ink_width
            elif style == "tile" and n[2] > 0.9:
                outline = shade(face.rgb, n, tint * 0.8)
        canvas.create_polygon(cam.flat(pts), fill=fill, outline=outline, width=width, tags=tags)
