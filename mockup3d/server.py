"""웹 API + 미리보기 UI.

실행: uvicorn mockup3d.server:app --reload
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import anthropic
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import printers, slicer
from .analyzer import Analyzer
from .jobs import Job
from .spec import MockupSpec

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = 25 * 1024 * 1024

app = FastAPI(title="AI Mockup → 3D Print")


@lru_cache
def analyzer() -> Analyzer:
    return Analyzer()


def _job(job_id: str) -> Job:
    try:
        job = Job(job_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not job.dir.exists():
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    return job


def _ai(call):
    try:
        return call()
    except anthropic.AuthenticationError:
        raise HTTPException(500, "ANTHROPIC_API_KEY가 설정되지 않았거나 올바르지 않습니다.")
    except anthropic.RateLimitError:
        raise HTTPException(429, "AI 호출 한도를 초과했습니다. 잠시 후 다시 시도하세요.")
    except anthropic.APIConnectionError:
        raise HTTPException(502, "AI 서버에 연결할 수 없습니다.")
    except anthropic.APIStatusError as e:
        raise HTTPException(502, f"AI 오류: {e.message}")
    except (RuntimeError, ValueError) as e:
        raise HTTPException(422, str(e))


@app.post("/api/jobs")
async def create_job(
    files: list[UploadFile] = File(...),
    notes: str = Form(""),
    source_type: str = Form("auto"),
    mode: str = Form("appearance"),
):
    job = Job.create()
    for f in files:
        data = await f.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, f"{f.filename}: 25MB 이하만 업로드할 수 있습니다.")
        job.save_input(f.filename or "input", data)
    spec = _ai(lambda: analyzer().analyze(job.inputs, notes, source_type, mode))
    return job.commit(spec)


@app.post("/api/jobs/manual")
def create_manual(spec: MockupSpec):
    """AI 없이 사양 JSON만으로 작업을 만든다."""
    return Job.create().commit(spec)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    return _job(job_id).summary()


class RefineRequest(BaseModel):
    instruction: str
    include_inputs: bool = True


@app.post("/api/jobs/{job_id}/refine")
def refine(job_id: str, body: RefineRequest):
    job = _job(job_id)
    files = job.inputs if body.include_inputs else []
    spec = _ai(lambda: analyzer().refine(job.latest_spec(), body.instruction, files))
    return job.commit(spec)


@app.put("/api/jobs/{job_id}/spec")
def put_spec(job_id: str, spec: MockupSpec):
    return _job(job_id).commit(spec)


@app.get("/api/jobs/{job_id}/files/{name}")
def get_file(job_id: str, name: str):
    path = _job(job_id).dir / "output" / Path(name).name
    if not path.exists():
        raise HTTPException(404, "파일이 없습니다.")
    return FileResponse(path, media_type="model/stl", filename=f"{job_id}_{path.name}")


class PrintRequest(BaseModel):
    file: str = "model.stl"
    config_ini: str | None = None
    start: bool = True


@app.post("/api/jobs/{job_id}/print")
def send_to_printer(job_id: str, body: PrintRequest):
    job = _job(job_id)
    report = job.summary()["report"]
    if not report["ok"]:
        raise HTTPException(409, "출력 검사에서 오류가 있어 전송하지 않았습니다.")
    printer = printers.from_env()
    if printer is None:
        raise HTTPException(503, "프린터가 설정되지 않았습니다 (MOCKUP3D_PRINTER, MOCKUP3D_PRINTER_URL).")
    stl = job.dir / "output" / Path(body.file).name
    if not stl.exists():
        raise HTTPException(404, "STL 파일이 없습니다.")
    try:
        gcode = slicer.slice_stl(stl, job.dir / "output" / f"{job.id}_{stl.stem}.gcode",
                                 body.config_ini, supports=report["needs_supports"])
    except slicer.SlicerNotFound as e:
        raise HTTPException(503, str(e))
    except RuntimeError as e:
        raise HTTPException(422, str(e))
    name = printer.upload(gcode, start=body.start)
    return {"uploaded": name, "started": body.start}


@app.get("/api/printer/status")
def printer_status():
    printer = printers.from_env()
    if printer is None:
        raise HTTPException(503, "프린터가 설정되지 않았습니다.")
    return printer.status()


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
