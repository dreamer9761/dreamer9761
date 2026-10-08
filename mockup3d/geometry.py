"""MockupSpec → 솔리드 모델(manifold3d CSG) → STL."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import manifold3d as m3d
import numpy as np

from .spec import MockupSpec, Part, Primitive

CIRCULAR_SEGMENTS = 64


@dataclass
class Mesh:
    vertices: np.ndarray  # (N, 3) float
    triangles: np.ndarray  # (M, 3) int

    @property
    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        return self.vertices.min(axis=0), self.vertices.max(axis=0)


def primitive_solid(p: Primitive) -> m3d.Manifold:
    if p.shape == "box":
        solid = m3d.Manifold.cube([p.size_x, p.size_y, p.size_z], center=True)
    elif p.shape == "cylinder":
        solid = m3d.Manifold.cylinder(p.size_z, p.size_x / 2, p.size_x / 2, CIRCULAR_SEGMENTS, center=True)
    elif p.shape == "cone":
        solid = m3d.Manifold.cylinder(p.size_z, p.size_x / 2, p.size_y / 2, CIRCULAR_SEGMENTS, center=True)
    elif p.shape == "sphere":
        solid = m3d.Manifold.sphere(p.size_x / 2, CIRCULAR_SEGMENTS)
    else:  # pragma: no cover - pydantic이 막아준다
        raise ValueError(f"unknown shape {p.shape}")
    if p.rot_x or p.rot_y or p.rot_z:
        solid = solid.rotate([p.rot_x, p.rot_y, p.rot_z])
    return solid.translate([p.x, p.y, p.z])


def union(solids: list[m3d.Manifold]) -> m3d.Manifold:
    if not solids:
        return m3d.Manifold()
    return m3d.Manifold.batch_boolean(solids, m3d.OpType.Add)


def build_part(part: Part) -> m3d.Manifold:
    adds = [primitive_solid(p) for p in part.primitives if p.operation == "add"]
    cuts = [primitive_solid(p) for p in part.primitives if p.operation == "cut"]
    solid = union(adds)
    if cuts:
        solid = solid - union(cuts)
    return solid


def build_model(spec: MockupSpec) -> m3d.Manifold:
    """전체 조립 모델. 바닥(z=0)에 놓이도록 내린다."""
    model = union([build_part(p) for p in spec.parts])
    if model.is_empty():
        return model
    (_, _, zmin, _, _, _) = model.bounding_box()
    return model.translate([0, 0, -zmin])


def to_mesh(solid: m3d.Manifold) -> Mesh:
    mesh = solid.to_mesh()
    return Mesh(
        vertices=np.asarray(mesh.vert_properties[:, :3], dtype=np.float64),
        triangles=np.asarray(mesh.tri_verts, dtype=np.int64),
    )


def write_stl(mesh: Mesh, path: str | Path, name: str = "mockup") -> Path:
    """바이너리 STL로 저장."""
    path = Path(path)
    tri = mesh.vertices[mesh.triangles]  # (M, 3, 3)
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.divide(normals, lengths, out=np.zeros_like(normals), where=lengths > 0)

    record = np.zeros(
        len(tri),
        dtype=[("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")],
    )
    record["normal"] = normals
    record["v"] = tri
    header = name.encode("ascii", "replace")[:80].ljust(80, b" ")
    with path.open("wb") as f:
        f.write(header)
        f.write(struct.pack("<I", len(tri)))
        f.write(record.tobytes())
    return path


def export(spec: MockupSpec, out_dir: str | Path) -> dict[str, Path]:
    """조립 모델 + 부품별 STL을 out_dir에 저장하고 경로를 반환."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {"model": write_stl(to_mesh(build_model(spec)), out_dir / "model.stl", spec.title)}
    for i, part in enumerate(spec.parts):
        solid = build_part(part)
        if solid.is_empty():
            continue
        files[f"part_{i}"] = write_stl(to_mesh(solid), out_dir / f"part_{i:02d}.stl", part.name)
    return files
