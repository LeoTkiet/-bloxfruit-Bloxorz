"""Builds the game's 3D assets: Wavefront OBJ models plus one shared MTL palette.

    python tools/build_models.py        # (re)writes assets/models/*.obj and palette.mtl

The models are low-poly and flat-shaded. Each one is a single convex solid (a box, or a pyramid
for the active-piece marker) with flat "decal" polygons painted on its faces. The game draws
them with its own Tkinter renderer (gui/render3d.py); they also open in Blender or any OBJ
viewer (import with Z up).

Conventions (gui/models.py reads the files with the same rules):
- 1 unit = 1 tile; z is up, +x is east (map columns), +y is south (map rows).
- Tiles fill x, y in [0, 1] with the walkable top at z = 0.
- Buggy (the block) is 1 x 1 x 2, feet at z = 0, face looking toward +y. The split pieces
  (head, legs) are unit cubes cut from the same block.
- Faces under `o <name>` form the solid; faces under `o <name>_decal` are paint, drawn after
  the solid in file order. Colours are the `Kd` entries of palette.mtl.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "assets" / "models"

ISLAND_DEPTH = 0.55   # land tiles reach down to the sea (gui/render3d.py: WATER_Z)
ICE_DEPTH = 0.2
BRIDGE_DEPTH = 0.12
DECAL_LIFT = 0.002    # paint floats just above its face so viewers don't z-fight

PALETTE = {
    # island
    "sand": "#ecd49a", "sand_dark": "#d4b67c", "earth": "#a88250", "earth_dark": "#6e5230",
    # thin ice
    "ice": "#d4f2ff", "ice_side": "#94cce8", "ice_crack": "#4e90bc", "ice_glint": "#ffffff",
    # wooden bridge
    "wood": "#b47c42", "wood_dark": "#83552a", "wood_side": "#6e4522", "nail": "#4a2c14",
    # treasure hole
    "hole": "#140c08", "hole_wall": "#3a2410", "hole_wall_dark": "#24160a",
    "gold": "#f4c64e", "gold_dark": "#b07e22", "gold_light": "#ffe9a0",
    # switches
    "soft": "#3a7ae0", "soft_dark": "#1c4a9c", "soft_light": "#a8d0ff",
    "heavy": "#e0402e", "heavy_dark": "#8c1c14",
    "split": "#a65ce0", "split_dark": "#5c2a92",
    # Buggy
    "skin": "#fff6ee", "skin_shadow": "#e8d4c4", "nose": "#e8202a", "nose_light": "#ffb0b0",
    "lips": "#b0102a", "hair": "#6cc8f4", "hair_dark": "#2e86c4", "hat": "#8c2434",
    "hat_dark": "#5a1622", "coat": "#d8432e", "coat_dark": "#93261a", "shirt": "#f6efe0",
    "stripe": "#2e86c4", "trousers": "#3c4a80", "boots": "#6a3c22", "hand": "#f8d4b0",
    "ink": "#181020",
}

Vec = tuple[float, float, float]


# ---- vector helpers ---------------------------------------------------------------------------
def _add(a: Vec, b: Vec) -> Vec:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _sub(a: Vec, b: Vec) -> Vec:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _mul(a: Vec, k: float) -> Vec:
    return a[0] * k, a[1] * k, a[2] * k


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _newell(points: list[Vec]) -> Vec:
    """Normal of a planar polygon from its winding (not normalised)."""
    nx = ny = nz = 0.0
    for (x0, y0, z0), (x1, y1, z1) in zip(points, points[1:] + points[:1]):
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    return nx, ny, nz


# ---- 2D shapes for decals, in face coordinates (u to the right, v up, seen from outside) ------
def rect(u0, v0, u1, v1):
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def circle(cu, cv, r, n=16):
    return [(cu + r * math.cos(2 * math.pi * i / n), cv + r * math.sin(2 * math.pi * i / n))
            for i in range(n)]


def bar(p, q, width):
    """A straight stroke from p to q."""
    du, dv = q[0] - p[0], q[1] - p[1]
    k = width / 2 / math.hypot(du, dv)
    nu, nv = -dv * k, du * k
    return [(p[0] + nu, p[1] + nv), (p[0] - nu, p[1] - nv), (q[0] - nu, q[1] - nv),
            (q[0] + nu, q[1] + nv)]


def arc(cu, cv, r_in, r_out, a0, a1, n=8):
    """A thick arc from angle a0 to a1 (degrees, counter-clockwise from +u)."""
    angles = [math.radians(a0 + (a1 - a0) * i / n) for i in range(n + 1)]
    outer = [(cu + r_out * math.cos(a), cv + r_out * math.sin(a)) for a in angles]
    inner = [(cu + r_in * math.cos(a), cv + r_in * math.sin(a)) for a in reversed(angles)]
    return outer + inner


def x_mark(cu, cv, length, width):
    h = length / 2 / math.sqrt(2)
    return [bar((cu - h, cv - h), (cu + h, cv + h), width),
            bar((cu - h, cv + h), (cu + h, cv - h), width)]


def strokes(points, width):
    return [bar(p, q, width) for p, q in zip(points, points[1:])]


def shifted(shape, du, dv):
    return [(u + du, v + dv) for u, v in shape]


def mirrored(shape, width=1.0):
    return [(width - u, v) for u, v in reversed(shape)]


# ---- meshes -----------------------------------------------------------------------------------
class Frame:
    """A box face: `origin` is its bottom-left corner seen from outside, `right`/`up` unit axes."""

    def __init__(self, origin: Vec, right: Vec, up: Vec, normal: Vec, width: float, height: float):
        self.origin, self.right, self.up, self.normal = origin, right, up, normal
        self.width, self.height = width, height

    def point(self, u: float, v: float) -> Vec:
        return _add(self.origin, _add(_mul(self.right, u), _mul(self.up, v)))

    def corners(self) -> list[Vec]:
        return [self.point(0, 0), self.point(self.width, 0), self.point(self.width, self.height),
                self.point(0, self.height)]


def box_frames(lo: Vec, hi: Vec) -> dict[str, Frame]:
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    w, d, h = x1 - x0, y1 - y0, z1 - z0
    return {
        "top": Frame((x0, y1, z1), (1, 0, 0), (0, -1, 0), (0, 0, 1), w, d),
        "bottom": Frame((x0, y0, z0), (1, 0, 0), (0, 1, 0), (0, 0, -1), w, d),
        "south": Frame((x0, y1, z0), (1, 0, 0), (0, 0, 1), (0, 1, 0), w, h),
        "north": Frame((x1, y0, z0), (-1, 0, 0), (0, 0, 1), (0, -1, 0), w, h),
        "east": Frame((x1, y1, z0), (0, -1, 0), (0, 0, 1), (1, 0, 0), d, h),
        "west": Frame((x0, y0, z0), (0, 1, 0), (0, 0, 1), (-1, 0, 0), d, h),
    }


class Mesh:
    def __init__(self, name: str):
        self.name = name
        self.verts: list[Vec] = []
        self._index: dict[Vec, int] = {}
        self.parts: dict[str, list[tuple[str, list[int]]]] = {"base": [], "decal": []}

    def _vertex(self, p: Vec) -> int:
        key = tuple(round(c, 4) + 0.0 for c in p)
        if key not in self._index:
            self.verts.append(key)
            self._index[key] = len(self.verts)
        return self._index[key]

    def poly(self, points: list[Vec], material: str, outward: Vec, decal: bool = False) -> None:
        if material not in PALETTE:
            raise KeyError(f"{self.name}: unknown material {material!r}")
        if _dot(_newell(points), outward) < 0:      # wind counter-clockwise seen from outside
            points = points[::-1]
        if decal:
            points = [_add(p, _mul(outward, DECAL_LIFT)) for p in points]
        self.parts["decal" if decal else "base"].append(
            (material, [self._vertex(p) for p in points]))

    def box(self, lo: Vec, hi: Vec, materials: dict[str, str]) -> dict[str, Frame]:
        frames = box_frames(lo, hi)
        for side, frame in frames.items():
            self.poly(frame.corners(), materials[side], frame.normal)
        return frames

    def decal(self, frame: Frame, shape, material: str) -> None:
        self.poly([frame.point(u, v) for u, v in shape], material, frame.normal, decal=True)

    def decals(self, frame: Frame, shapes, material: str) -> None:
        for shape in shapes:
            self.decal(frame, shape, material)

    def obj_text(self) -> str:
        lines = [f"# Bloxorz 3D asset: {self.name} (generated by tools/build_models.py)",
                 "# 1 unit = 1 tile, Z up, +X east, +Y south", "mtllib palette.mtl"]
        lines += [f"v {_num(x)} {_num(y)} {_num(z)}" for x, y, z in self.verts]
        for part, faces in self.parts.items():
            if not faces:
                continue
            lines.append(f"o {self.name}" + ("_decal" if part == "decal" else ""))
            current = None
            for material, indices in faces:
                if material != current:
                    lines.append(f"usemtl {material}")
                    current = material
                lines.append("f " + " ".join(map(str, indices)))
        return "\n".join(lines) + "\n"


def _num(x: float) -> str:
    text = f"{x:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def mtl_text() -> str:
    lines = ["# Bloxorz 3D asset palette (generated by tools/build_models.py)"]
    for name, color in PALETTE.items():
        r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
        lines += ["", f"newmtl {name}", f"Kd {r:.4f} {g:.4f} {b:.4f}"]
    return "\n".join(lines) + "\n"


# ---- tiles ------------------------------------------------------------------------------------
SIDES = ("north", "south", "east", "west")


def island(name: str) -> tuple[Mesh, Frame]:
    """A sand-topped island block reaching down to the sea; returns the mesh and its top face."""
    mesh = Mesh(name)
    frames = mesh.box((0, 0, -ISLAND_DEPTH), (1, 1, 0),
                      {"top": "sand", "bottom": "earth_dark", **{s: "earth" for s in SIDES}})
    d = ISLAND_DEPTH
    for side in SIDES:
        mesh.decal(frames[side], rect(0, d - 0.09, 1, d), "sand_dark")
        mesh.decal(frames[side], rect(0, d * 0.42, 1, d * 0.42 + 0.04), "earth_dark")
    return mesh, frames["top"]


def floor() -> Mesh:
    mesh, top = island("floor")
    mesh.decals(top, [rect(0.2, 0.68, 0.26, 0.74), rect(0.7, 0.24, 0.76, 0.3)], "sand_dark")
    return mesh


def goal() -> Mesh:
    mesh, top = island("goal")
    mesh.decal(top, rect(0.08, 0.08, 0.92, 0.92), "gold_dark")
    mesh.decal(top, rect(0.12, 0.12, 0.88, 0.88), "gold")
    mesh.decal(top, rect(0.18, 0.18, 0.82, 0.82), "hole")
    mesh.decal(top, [(0.18, 0.82), (0.82, 0.82), (0.76, 0.68), (0.24, 0.68)], "hole_wall")
    mesh.decal(top, [(0.82, 0.18), (0.82, 0.82), (0.76, 0.68), (0.76, 0.28)], "hole_wall_dark")
    mesh.decals(top, [circle(0.44, 0.36, 0.05, 10), circle(0.5, 0.29, 0.045, 10)], "gold")
    mesh.decal(top, circle(0.57, 0.41, 0.05, 10), "gold_dark")
    return mesh


def fragile() -> Mesh:
    mesh = Mesh("fragile")
    frames = mesh.box((0, 0, -ICE_DEPTH), (1, 1, 0),
                      {"top": "ice", "bottom": "ice_side", **{s: "ice_side" for s in SIDES}})
    top = frames["top"]
    mesh.decals(top, strokes([(0.15, 0.7), (0.32, 0.58), (0.45, 0.63), (0.6, 0.45), (0.8, 0.36)],
                             0.03), "ice_crack")
    mesh.decals(top, strokes([(0.45, 0.63), (0.52, 0.85)], 0.025), "ice_crack")
    mesh.decals(top, strokes([(0.6, 0.45), (0.55, 0.2), (0.4, 0.12)], 0.025), "ice_crack")
    mesh.decal(top, [(0.1, 0.78), (0.2, 0.78), (0.3, 0.9), (0.2, 0.9)], "ice_glint")
    for side in SIDES:
        mesh.decal(frames[side], rect(0, ICE_DEPTH - 0.04, 1, ICE_DEPTH), "ice_glint")
    return mesh


def bridge() -> Mesh:
    mesh = Mesh("bridge")
    frames = mesh.box((0, 0, -BRIDGE_DEPTH), (1, 1, 0),
                      {"top": "wood", "bottom": "wood_side", **{s: "wood_side" for s in SIDES}})
    top = frames["top"]
    for v in (0.25, 0.5, 0.75):
        mesh.decal(top, rect(0, v - 0.018, 1, v + 0.018), "wood_dark")
    for v in (0.125, 0.375, 0.625, 0.875):
        mesh.decals(top, [rect(0.06, v - 0.03, 0.11, v + 0.03), rect(0.89, v - 0.03, 0.94, v + 0.03)],
                    "nail")
    return mesh


def soft_switch() -> Mesh:
    mesh, top = island("soft_switch")
    mesh.decal(top, circle(0.53, 0.53, 0.29), "soft_dark")      # shade: light comes from the SW
    mesh.decal(top, circle(0.5, 0.5, 0.28), "soft")
    mesh.decal(top, circle(0.42, 0.42, 0.07, 10), "soft_light")
    return mesh


def heavy_switch() -> Mesh:
    mesh, top = island("heavy_switch")
    mesh.decals(top, [shifted(s, 0.03, 0.03) for s in x_mark(0.5, 0.5, 0.74, 0.22)], "heavy_dark")
    mesh.decals(top, x_mark(0.5, 0.5, 0.7, 0.17), "heavy")
    return mesh


def split_switch() -> Mesh:
    mesh, top = island("split_switch")
    mesh.decal(top, circle(0.5, 0.5, 0.37), "sand_dark")
    for a0, a1 in ((125, 235), (-55, 55)):
        mesh.decal(top, shifted(arc(0.5, 0.5, 0.2, 0.29, a0, a1), 0.025, 0.025), "split_dark")
        mesh.decal(top, arc(0.5, 0.5, 0.2, 0.29, a0, a1), "split")
    return mesh


# ---- Buggy ------------------------------------------------------------------------------------
# Side paint in block coordinates: u across the face (0..1), v = height on the block (0..2).
# The face (v > 1) is the head piece after a split, the rest is the legs piece; no shape
# crosses v = 1. "side" shapes are drawn as seen on the east face (u = 0 at the front); the
# west face gets them mirrored.
def _buggy_sides() -> dict[str, list[tuple[list, str]]]:
    every = [(rect(0, 0, 1, 0.2), "boots"), (rect(0, 0.2, 1, 0.5), "trousers"),
             (rect(0, 0.56, 1, 1.0), "coat"), (rect(0, 0.56, 1, 0.6), "coat_dark"),
             (rect(0, 0.48, 1, 0.56), "ink"), (rect(0, 1.84, 1, 2.0), "hat"),
             (rect(0, 1.84, 1, 1.87), "gold")]
    front = [
        (rect(0.3, 0.2, 0.36, 0.48), "stripe"), (rect(0.64, 0.2, 0.7, 0.48), "stripe"),
        (rect(0.34, 0.6, 0.66, 1.0), "shirt"),
        *[(rect(0.34, v, 0.66, v + 0.05), "stripe") for v in (0.66, 0.78, 0.9)],
        *[(rect(u, v, u + 0.05, v + 0.05), "gold") for u in (0.25, 0.7) for v in (0.7, 0.84)],
        (rect(0.43, 0.47, 0.57, 0.57), "gold"), (rect(0.47, 0.5, 0.53, 0.54), "ink"),
        (rect(0, 1.3, 0.12, 1.84), "hair"), (rect(0.88, 1.3, 1, 1.84), "hair"),
        (rect(0, 1.74, 1, 1.84), "hair"),
        *[([(u, 1.74), (u + 0.1, 1.64), (u + 0.2, 1.74)], "hair") for u in (0.12, 0.4, 0.68)],
        (rect(0.27, 1.5, 0.37, 1.62), "ink"), (rect(0.63, 1.5, 0.73, 1.62), "ink"),
        (bar((0.24, 1.68), (0.4, 1.65), 0.035), "ink"), (bar((0.6, 1.65), (0.76, 1.68), 0.035), "ink"),
        (arc(0.5, 1.38, 0.19, 0.25, 200, 340), "lips"),
        (circle(0.5, 1.42, 0.13), "nose"), (circle(0.46, 1.46, 0.04, 10), "nose_light"),
    ]
    back = [(rect(0.48, 0.6, 0.52, 1.0), "coat_dark"), (rect(0, 1.0, 1, 1.84), "hair"),
            *[(rect(u, 1.0, u + 0.06, 1.84), "hair_dark") for u in (0.2, 0.5, 0.78)]]
    side = [(rect(0.34, 0.62, 0.66, 0.98), "coat_dark"), (rect(0.38, 0.52, 0.62, 0.62), "hand"),
            (rect(0.45, 1.2, 1, 1.84), "hair"), (rect(0.6, 1.2, 0.66, 1.84), "hair_dark"),
            (circle(0.36, 1.45, 0.07, 10), "skin_shadow")]
    return {"south": every + front, "north": every + back,
            "east": every + side, "west": every + [(mirrored(s), m) for s, m in side]}


BUGGY_SIDES = _buggy_sides()
BUGGY_TOP = [  # the captain's hat with his red-nosed Jolly Roger
    (rect(0.08, 0.08, 0.92, 0.92), "gold"), (rect(0.14, 0.14, 0.86, 0.86), "hat"),
    (bar((0.3, 0.26), (0.7, 0.44), 0.06), "skin"), (bar((0.3, 0.44), (0.7, 0.26), 0.06), "skin"),
    (circle(0.5, 0.58, 0.16), "skin"), (rect(0.41, 0.4, 0.59, 0.5), "skin"),
    (rect(0.42, 0.56, 0.48, 0.64), "ink"), (rect(0.52, 0.56, 0.58, 0.64), "ink"),
    (circle(0.5, 0.51, 0.035, 8), "nose"),
]
BUGGY_SOLES = [(rect(0.12, 0.15, 0.44, 0.85), "boots"), (rect(0.56, 0.15, 0.88, 0.85), "boots")]


def _paint_buggy(mesh: Mesh, frames: dict[str, Frame], lo: float, hi: float) -> None:
    """Paint the part of Buggy between block heights lo..hi on a box whose bottom is at lo."""
    for side, shapes in BUGGY_SIDES.items():
        for shape, material in shapes:
            vs = [v for _, v in shape]
            if min(vs) >= lo - 1e-9 and max(vs) <= hi + 1e-9:
                mesh.decal(frames[side], shifted(shape, 0, -lo), material)
    if hi == 2:
        for shape, material in BUGGY_TOP:
            mesh.decal(frames["top"], shape, material)
    if lo == 0:
        for shape, material in BUGGY_SOLES:
            mesh.decal(frames["bottom"], shape, material)


def buggy() -> Mesh:
    mesh = Mesh("buggy")
    frames = mesh.box((0, 0, 0), (1, 1, 2),
                      {"top": "hat", "bottom": "ink", **{s: "skin" for s in SIDES}})
    _paint_buggy(mesh, frames, 0, 2)
    return mesh


def buggy_head() -> Mesh:
    mesh = Mesh("buggy_head")
    frames = mesh.box((0, 0, 0), (1, 1, 1),
                      {"top": "hat", "bottom": "coat_dark", **{s: "skin" for s in SIDES}})
    _paint_buggy(mesh, frames, 1, 2)
    mesh.decal(frames["bottom"], circle(0.5, 0.5, 0.22), "skin_shadow")
    return mesh


def buggy_legs() -> Mesh:
    mesh = Mesh("buggy_legs")
    frames = mesh.box((0, 0, 0), (1, 1, 1),
                      {"top": "coat_dark", "bottom": "ink", **{s: "coat" for s in SIDES}})
    _paint_buggy(mesh, frames, 0, 1)
    mesh.decal(frames["top"], rect(0.34, 0.25, 0.66, 0.75), "shirt")
    return mesh


def marker() -> Mesh:
    """The gold arrow floating over the active piece: a pyramid pointing down."""
    mesh = Mesh("marker")
    lo, hi, z = 0.25, 0.75, 0.55
    top = [(lo, lo, z), (hi, lo, z), (hi, hi, z), (lo, hi, z)]
    apex = (0.5, 0.5, 0.0)
    mesh.poly(top, "gold_light", (0, 0, 1))
    centre = (0.5, 0.5, z * 0.75)
    for a, b in zip(top, top[1:] + top[:1]):
        tri = [a, b, apex]
        mid = _mul(_add(_add(a, b), apex), 1 / 3)
        mesh.poly(tri, "gold", _sub(mid, centre))
    return mesh


BUILDERS = (floor, goal, fragile, bridge, soft_switch, heavy_switch, split_switch,
            buggy, buggy_head, buggy_legs, marker)


def build_all() -> dict[str, str]:
    """File name -> text of every asset file."""
    files = {"palette.mtl": mtl_text()}
    for builder in BUILDERS:
        mesh = builder()
        files[f"{mesh.name}.obj"] = mesh.obj_text()
    return files


def main(argv=None) -> None:
    out = Path(argv[0]) if argv else OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    for name, text in build_all().items():
        (out / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {out / name}")


if __name__ == "__main__":
    main(sys.argv[1:])
