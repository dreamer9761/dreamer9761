"""STL → G-code 슬라이싱. PrusaSlicer CLI를 사용한다(설치 필요).

프린터별 설정은 PrusaSlicer에서 내보낸 .ini 프로필(Printer/Print/Filament 통합)을 넘긴다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

CANDIDATES = ("prusa-slicer", "PrusaSlicer", "prusa-slicer-console")


class SlicerNotFound(RuntimeError):
    pass


def find_slicer() -> str:
    explicit = os.environ.get("MOCKUP3D_SLICER")
    if explicit:
        return explicit
    for name in CANDIDATES:
        path = shutil.which(name)
        if path:
            return path
    raise SlicerNotFound(
        "PrusaSlicer CLI를 찾을 수 없습니다. 설치 후 PATH에 추가하거나 MOCKUP3D_SLICER 환경변수로 경로를 지정하세요."
    )


def slice_stl(
    stl: str | Path,
    out_gcode: str | Path,
    config_ini: str | Path | None = None,
    supports: bool = False,
    timeout: int = 600,
) -> Path:
    cmd = [find_slicer(), "--export-gcode"]
    if config_ini:
        cmd += ["--load", str(config_ini)]
    if supports:
        cmd += ["--support-material", "--support-material-auto"]
    cmd += ["--output", str(out_gcode), str(stl)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"슬라이싱 실패: {result.stderr.strip() or result.stdout.strip()}")
    return Path(out_gcode)
