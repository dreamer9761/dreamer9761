"""프린터 연동. OctoPrint와 Moonraker(Klipper)를 지원한다."""

from __future__ import annotations

import os

from .base import JobStatus, Printer
from .moonraker import MoonrakerPrinter
from .octoprint import OctoPrintPrinter

__all__ = ["JobStatus", "Printer", "MoonrakerPrinter", "OctoPrintPrinter", "from_env"]


def from_env() -> Printer | None:
    """MOCKUP3D_PRINTER=octoprint|moonraker, MOCKUP3D_PRINTER_URL, MOCKUP3D_PRINTER_API_KEY."""
    kind = os.environ.get("MOCKUP3D_PRINTER", "").lower()
    url = os.environ.get("MOCKUP3D_PRINTER_URL", "")
    key = os.environ.get("MOCKUP3D_PRINTER_API_KEY", "")
    if not kind or not url:
        return None
    if kind == "octoprint":
        return OctoPrintPrinter(url, key)
    if kind == "moonraker":
        return MoonrakerPrinter(url, key or None)
    raise ValueError(f"지원하지 않는 프린터 종류: {kind}")
