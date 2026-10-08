"""작업(job) 저장소: 업로드 파일, 사양 버전, 결과 STL, 검사 보고서를 디렉터리에 보관."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

from . import geometry, printability
from .spec import MockupSpec

DATA_DIR = Path(os.environ.get("MOCKUP3D_DATA", "data/jobs"))

_ID = re.compile(r"^[0-9a-f]{12}$")


class Job:
    def __init__(self, job_id: str, root: Path | None = None):
        if not _ID.match(job_id):
            raise ValueError("잘못된 작업 ID")
        self.id = job_id
        self.dir = (root or DATA_DIR) / job_id

    @classmethod
    def create(cls, root: Path | None = None) -> "Job":
        job = cls(uuid.uuid4().hex[:12], root)
        (job.dir / "inputs").mkdir(parents=True)
        return job

    @property
    def inputs(self) -> list[Path]:
        return sorted((self.dir / "inputs").glob("*"))

    def save_input(self, name: str, data: bytes) -> Path:
        safe = re.sub(r"[^\w.\-]", "_", Path(name).name) or "input"
        path = self.dir / "inputs" / safe
        path.write_bytes(data)
        return path

    def versions(self) -> list[int]:
        return sorted(int(p.stem.split("_")[1]) for p in self.dir.glob("spec_*.json"))

    def latest_spec(self) -> MockupSpec:
        versions = self.versions()
        if not versions:
            raise FileNotFoundError("아직 사양이 없습니다.")
        return MockupSpec.model_validate_json((self.dir / f"spec_{versions[-1]:03d}.json").read_text())

    def commit(self, spec: MockupSpec, printer: printability.PrinterProfile | None = None) -> dict:
        """새 사양 버전을 저장하고 STL과 검사 보고서를 만든다."""
        version = (self.versions() or [0])[-1] + 1
        (self.dir / f"spec_{version:03d}.json").write_text(spec.model_dump_json(indent=2))
        report = printability.check(spec, printer)
        out = self.dir / "output"
        for old in out.glob("*.stl"):
            old.unlink()
        files = geometry.export(spec, out) if report.size_mm != [0, 0, 0] else {}
        (self.dir / "report.json").write_text(report.model_dump_json(indent=2))
        return self.summary(spec, report, sorted(p.name for p in files.values()), version)

    def summary(self, spec=None, report=None, files=None, version=None) -> dict:
        spec = spec or self.latest_spec()
        if report is None:
            report = printability.Report.model_validate_json((self.dir / "report.json").read_text())
        if files is None:
            files = sorted(p.name for p in (self.dir / "output").glob("*.stl"))
        return {
            "id": self.id,
            "version": version or self.versions()[-1],
            "spec": json.loads(spec.model_dump_json()),
            "report": json.loads(report.model_dump_json()),
            "files": files,
            "inputs": [p.name for p in self.inputs],
        }
