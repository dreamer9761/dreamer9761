"""출력 전 검사: 크기, 닫힌 형상, 얇은 부분, 오버행(지지대 필요 여부), 재료량."""

from __future__ import annotations

import os
from dataclasses import dataclass

import manifold3d as m3d
import numpy as np
from pydantic import BaseModel

from .geometry import primitive_solid, union, build_model, build_part, to_mesh
from .spec import MockupSpec


@dataclass
class PrinterProfile:
    name: str = "Generic FDM 220x220x250"
    bed_x: float = 220.0
    bed_y: float = 220.0
    max_z: float = 250.0
    nozzle_mm: float = 0.4
    min_wall_mm: float = 1.2  # 노즐 3줄
    min_hole_mm: float = 2.0
    overhang_deg: float = 45.0
    filament_density: float = 1.24  # PLA g/cm³
    effective_fill: float = 0.35  # 벽+15~20% 인필 가정 시 대략적 충전율


PRESETS: dict[str, PrinterProfile] = {
    "generic": PrinterProfile(),
    # QIDI Q2: 밀폐형 CoreXY, Klipper + Moonraker(포트 7125) 기본 탑재
    "qidi_q2": PrinterProfile(name="QIDI Q2", bed_x=270.0, bed_y=270.0, max_z=256.0),
}


def default_profile() -> PrinterProfile:
    """MOCKUP3D_PRINTER_PROFILE 환경변수로 고른 프린터 프로필 (기본 generic)."""
    key = os.environ.get("MOCKUP3D_PRINTER_PROFILE", "generic").lower()
    if key not in PRESETS:
        raise ValueError(f"알 수 없는 프린터 프로필 {key!r}. 사용 가능: {', '.join(PRESETS)}")
    return PRESETS[key]


class Issue(BaseModel):
    level: str  # "error" | "warning" | "info"
    code: str
    message: str


class Report(BaseModel):
    ok: bool
    size_mm: list[float]
    volume_cm3: float
    est_filament_g: float
    triangles: int
    overhang_area_ratio: float
    needs_supports: bool
    issues: list[Issue]


def _required_sizes(p) -> tuple[float, ...]:
    if p.shape == "box":
        return (p.size_x, p.size_y, p.size_z)
    if p.shape == "cylinder":
        return (p.size_x, p.size_z)
    if p.shape == "cone":
        return (max(p.size_x, p.size_y), p.size_z)
    return (p.size_x,)


def _min_feature(p) -> float:
    if p.shape == "box":
        return min(p.size_x, p.size_y, p.size_z)
    if p.shape == "cylinder":
        return min(p.size_x, p.size_z)
    if p.shape == "cone":
        return min(max(p.size_x, p.size_y), p.size_z)
    return p.size_x


def check(spec: MockupSpec, printer: PrinterProfile | None = None) -> Report:
    printer = printer or default_profile()
    issues: list[Issue] = []

    for part in spec.parts:
        for p in part.primitives:
            if min(_required_sizes(p)) <= 0:
                issues.append(Issue(level="error", code="non_positive_size",
                                    message=f"[{part.name}] '{p.label}' 치수가 0 이하입니다."))
                continue
            feat = _min_feature(p)
            if p.operation == "add" and feat < printer.min_wall_mm:
                issues.append(Issue(level="warning", code="thin_feature",
                                    message=f"[{part.name}] '{p.label}' 최소 두께 {feat:.2f}mm < 권장 {printer.min_wall_mm}mm"))
            if p.operation == "cut" and p.shape in ("cylinder", "cone") and feat < printer.min_hole_mm:
                issues.append(Issue(level="warning", code="small_hole",
                                    message=f"[{part.name}] '{p.label}' 구멍 지름 {feat:.2f}mm는 막힐 수 있습니다 (권장 ≥ {printer.min_hole_mm}mm)"))
        body = union([primitive_solid(p) for p in part.primitives if p.operation == "add"])
        for p in part.primitives:
            if p.operation == "cut" and min(_required_sizes(p)) > 0 and (body ^ primitive_solid(p)).is_empty():
                issues.append(Issue(level="warning", code="cut_no_effect",
                                    message=f"[{part.name}] '{p.label}' 제거 형상이 본체와 겹치지 않아 아무 효과가 없습니다."))
        solid = build_part(part)
        if solid.is_empty():
            issues.append(Issue(level="error", code="empty_part", message=f"[{part.name}] 형상이 비어 있습니다."))
        elif len(solid.decompose()) > 1:
            issues.append(Issue(level="warning", code="disconnected",
                                message=f"[{part.name}] 서로 떨어진 조각 {len(solid.decompose())}개로 출력됩니다."))

    model = build_model(spec)
    if model.is_empty():
        issues.append(Issue(level="error", code="empty_model", message="모델이 비어 있습니다."))
        return Report(ok=False, size_mm=[0, 0, 0], volume_cm3=0, est_filament_g=0, triangles=0,
                      overhang_area_ratio=0, needs_supports=False, issues=issues)
    if model.status() != m3d.Error.NoError:
        issues.append(Issue(level="error", code="invalid_mesh", message=f"형상 오류: {model.status()}"))

    mesh = to_mesh(model)
    lo, hi = mesh.bounds
    size = (hi - lo).tolist()
    fits_flat = size[0] <= printer.bed_x and size[1] <= printer.bed_y
    fits_rotated = size[1] <= printer.bed_x and size[0] <= printer.bed_y
    if not (fits_flat or fits_rotated) or size[2] > printer.max_z:
        issues.append(Issue(level="error", code="too_large",
                            message=f"크기 {size[0]:.1f}×{size[1]:.1f}×{size[2]:.1f}mm가 프린터 "
                                    f"{printer.bed_x:.0f}×{printer.bed_y:.0f}×{printer.max_z:.0f}mm를 넘습니다. 축소하거나 분할하세요."))
    elif fits_rotated and not fits_flat:
        issues.append(Issue(level="info", code="rotate_on_bed", message="베드에서 90° 회전하면 출력 가능합니다."))

    # 오버행: 아래를 향하면서 베드에 닿지 않는 면
    tri = mesh.vertices[mesh.triangles]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area2 = np.linalg.norm(n, axis=1)
    nz = np.divide(n[:, 2], area2, out=np.zeros_like(area2), where=area2 > 0)
    on_bed = tri[:, :, 2].max(axis=1) <= lo[2] + 0.2
    overhang = (nz < -np.cos(np.radians(90 - printer.overhang_deg))) & ~on_bed
    ratio = float(area2[overhang].sum() / area2.sum()) if area2.sum() else 0.0
    needs_supports = ratio > 0.005
    if needs_supports:
        issues.append(Issue(level="info", code="supports",
                            message=f"오버행 면적 {ratio * 100:.1f}% — 지지대가 필요하거나 출력 방향을 바꾸세요."))

    volume_cm3 = model.volume() / 1000.0
    grams = volume_cm3 * printer.filament_density * printer.effective_fill
    return Report(
        ok=not any(i.level == "error" for i in issues),
        size_mm=[round(v, 2) for v in size],
        volume_cm3=round(volume_cm3, 2),
        est_filament_g=round(grams, 1),
        triangles=int(len(mesh.triangles)),
        overhang_area_ratio=round(ratio, 4),
        needs_supports=needs_supports,
        issues=issues,
    )
