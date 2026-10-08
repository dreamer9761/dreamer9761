"""OctoPrint REST API (https://docs.octoprint.org/en/master/api/)."""

from __future__ import annotations

from pathlib import Path

import httpx

from .base import JobStatus


class OctoPrintPrinter:
    def __init__(self, base_url: str, api_key: str, client: httpx.Client | None = None):
        self.client = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=60)
        self.client.headers["X-Api-Key"] = api_key

    def upload(self, gcode: Path, start: bool = True) -> str:
        gcode = Path(gcode)
        with gcode.open("rb") as f:
            r = self.client.post(
                "/api/files/local",
                files={"file": (gcode.name, f, "application/octet-stream")},
                data={"select": "true", "print": "true" if start else "false"},
            )
        r.raise_for_status()
        return gcode.name

    def status(self) -> JobStatus:
        r = self.client.get("/api/job")
        r.raise_for_status()
        body = r.json()
        return JobStatus(
            state=body.get("state", "unknown"),
            file=(body.get("job") or {}).get("file", {}).get("name"),
            progress=(body.get("progress") or {}).get("completion"),
            time_left_s=(body.get("progress") or {}).get("printTimeLeft"),
        )

    def cancel(self) -> None:
        self.client.post("/api/job", json={"command": "cancel"}).raise_for_status()
