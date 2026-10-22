"""3D assets: loads the Wavefront OBJ models in assets/models/ (built by tools/build_models.py).

Rules shared with the generator, and with anyone who edits the models in Blender:
- 1 unit = 1 tile; z is up, +x is east (map columns), +y is south (map rows).
- Tiles fill x, y in [0, 1] with the walkable top at z = 0. Buggy is 1 x 1 x 2 with his feet
  at z = 0 and his face toward +y; the split pieces are unit cubes.
- Each model is one convex solid. Faces of an object whose name contains "decal" are flat
  paint on a solid face: they are drawn after the solid, in file order.
- Colours are the `Kd` entries of the .mtl files named by `mtllib`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parents[1] / "assets" / "models"

Vec = tuple[float, float, float]
RGB = tuple[float, float, float]


@dataclass(frozen=True)
class Face:
    points: tuple[Vec, ...]
    normal: Vec          # unit, pointing out of the solid
    rgb: RGB
    decal: bool


@dataclass(frozen=True)
class Model:
    name: str
    faces: tuple[Face, ...]   # solid faces first, then decals in drawing order
    lo: Vec                   # bounding box
    hi: Vec

    @property
    def center(self) -> Vec:
        return tuple((a + b) / 2 for a, b in zip(self.lo, self.hi))

    @property
    def depth(self) -> float:
        """How far a tile reaches below its top (z = 0)."""
        return -self.lo[2]


def _normal(points: list[Vec]) -> Vec | None:
    nx = ny = nz = 0.0
    for (x0, y0, z0), (x1, y1, z1) in zip(points, points[1:] + points[:1]):
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    return None if length < 1e-12 else (nx / length, ny / length, nz / length)


def load_mtl(path: Path) -> dict[str, RGB]:
    colors, name = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "newmtl":
            name = " ".join(parts[1:])
        elif parts[0] == "Kd" and name is not None:
            colors[name] = tuple(float(x) for x in parts[1:4])
    return colors


def load_obj(path: Path) -> Model:
    path = Path(path)
    verts: list[Vec] = []
    colors: dict[str, RGB] = {}
    solid, decals = [], []
    rgb: RGB = (0.8, 0.8, 0.8)
    is_decal = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        key = parts[0]
        if key == "v":
            verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif key == "mtllib":
            colors.update(load_mtl(path.parent / " ".join(parts[1:])))
        elif key == "usemtl":
            name = " ".join(parts[1:])
            if name not in colors:
                raise ValueError(f"{path.name}:{number}: unknown material {name!r}")
            rgb = colors[name]
        elif key in ("o", "g"):
            is_decal = "decal" in " ".join(parts[1:]).lower()
        elif key == "f":
            points = []
            for ref in parts[1:]:
                i = int(ref.split("/")[0])
                points.append(verts[i - 1 if i > 0 else len(verts) + i])
            normal = _normal(points)
            if normal is not None:
                (decals if is_decal else solid).append(Face(tuple(points), normal, rgb, is_decal))
    if not solid:
        raise ValueError(f"{path.name}: no solid faces")
    every = [p for face in solid for p in face.points]
    lo = tuple(min(p[i] for p in every) for i in range(3))
    hi = tuple(max(p[i] for p in every) for i in range(3))
    return Model(path.stem, tuple(solid + decals), lo, hi)


@lru_cache(maxsize=None)
def get(name: str) -> Model:
    path = MODELS_DIR / f"{name}.obj"
    if not path.is_file():
        raise FileNotFoundError(f"missing 3D asset {path} - run `python tools/build_models.py`")
    return load_obj(path)
