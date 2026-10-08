"""Moonraker(Klipper) API (https://moonraker.readthedocs.io/en/latest/web_api/)."""

from __future__ import annotations

from pathlib import Path

import httpx

from .base import JobStatus


class MoonrakerPrinter:
    def __init__(self, base_url: str, api_key: str | None = None, client: httpx.Client | None = None):
        self.client = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=60)
        if api_key:
            self.client.headers["X-Api-Key"] = api_key

    def upload(self, gcode: Path, start: bool = True) -> str:
        gcode = Path(gcode)
        with gcode.open("rb") as f:
            r = self.client.post(
                "/server/files/upload",
                files={"file": (gcode.name, f, "application/octet-stream")},
                data={"root": "gcodes", "print": "true" if start else "false"},
            )
        r.raise_for_status()
        return gcode.name

    def status(self) -> JobStatus:
        r = self.client.get("/printer/objects/query", params={"print_stats": "", "display_status": ""})
        r.raise_for_status()
        st = r.json()["result"]["status"]
        stats, display = st.get("print_stats", {}), st.get("display_status", {})
        progress = display.get("progress")
        return JobStatus(
            state=stats.get("state", "unknown"),
            file=stats.get("filename") or None,
            progress=progress * 100 if progress is not None else None,
        )

    def cancel(self) -> None:
        self.client.post("/printer/print/cancel").raise_for_status()
