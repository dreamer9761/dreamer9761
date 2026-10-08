from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class JobStatus(BaseModel):
    state: str  # printer-reported state text
    file: str | None = None
    progress: float | None = None  # 0~100
    time_left_s: float | None = None


class Printer(Protocol):
    def upload(self, gcode: Path, start: bool = True) -> str: ...

    def status(self) -> JobStatus: ...

    def cancel(self) -> None: ...
