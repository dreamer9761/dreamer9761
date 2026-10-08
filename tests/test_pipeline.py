import json
import struct
from pathlib import Path
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from mockup3d import geometry, printability
from mockup3d.printers import MoonrakerPrinter, OctoPrintPrinter
from mockup3d.spec import MockupSpec, Part, Primitive

EXAMPLE = Path(__file__).parent.parent / "examples" / "phone_stand.json"


def box(label, sx, sy, sz, op="add", **kw):
    return Primitive(label=label, shape="box", operation=op, size_x=sx, size_y=sy, size_z=sz, **kw)


def spec_of(*prims, **kw):
    return MockupSpec(title="t", source_type="manual", mode="appearance",
                      parts=[Part(name="p", primitives=list(prims))], **kw)


def test_plate_with_hole_volume_and_bed_placement():
    hole = Primitive(label="hole", shape="cylinder", operation="cut", size_x=10, size_y=10, size_z=12, z=50)
    model = geometry.build_model(spec_of(box("plate", 40, 30, 5, z=50), hole))
    expected = 40 * 30 * 5 - np.pi * 25 * 5
    assert model.volume() == pytest.approx(expected, rel=0.01)
    assert model.bounding_box()[2] == pytest.approx(0)  # 바닥에 내려놓음


def test_stl_is_valid_binary(tmp_path):
    mesh = geometry.to_mesh(geometry.build_model(spec_of(box("b", 10, 10, 10))))
    path = geometry.write_stl(mesh, tmp_path / "b.stl")
    data = path.read_bytes()
    (count,) = struct.unpack("<I", data[80:84])
    assert count == len(mesh.triangles) == 12
    assert len(data) == 84 + 50 * count


def test_example_spec_is_printable(tmp_path):
    spec = MockupSpec.model_validate_json(EXAMPLE.read_text())
    report = printability.check(spec)
    assert report.ok, report.issues
    files = geometry.export(spec, tmp_path)
    assert set(files) == {"model", "part_0", "part_1", "part_2"}


def test_checks_flag_size_thin_wall_and_small_hole():
    hole = Primitive(label="pin", shape="cylinder", operation="cut", size_x=1, size_y=1, size_z=10)
    report = printability.check(spec_of(box("huge", 300, 50, 0.8), hole))
    codes = {i.code for i in report.issues}
    assert {"too_large", "thin_feature", "small_hole"} <= codes
    assert not report.ok


def test_checks_flag_cut_that_misses_body():
    miss = Primitive(label="hole", shape="cylinder", operation="cut", size_x=5, size_y=5, size_z=5, z=100)
    assert "cut_no_effect" in {i.code for i in printability.check(spec_of(box("b", 10, 10, 10), miss)).issues}


def test_checks_detect_overhang_and_disconnected():
    # T자: 위쪽 판이 기둥보다 넓어 아래를 향한 면이 공중에 떠 있다
    t = spec_of(box("post", 10, 10, 30, z=15), box("top", 60, 10, 4, z=32))
    assert printability.check(t).needs_supports
    apart = spec_of(box("a", 10, 10, 10), box("b", 10, 10, 10, x=50))
    assert "disconnected" in {i.code for i in printability.check(apart).issues}


def test_octoprint_upload_and_status(tmp_path):
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        if request.url.path == "/api/files/local":
            return httpx.Response(201, json={"done": True})
        return httpx.Response(200, json={"state": "Printing", "job": {"file": {"name": "a.gcode"}},
                                         "progress": {"completion": 42.0, "printTimeLeft": 600}})

    client = httpx.Client(base_url="http://octo", transport=httpx.MockTransport(handler))
    printer = OctoPrintPrinter("http://octo", "KEY", client=client)
    gcode = tmp_path / "a.gcode"
    gcode.write_text("G28\n")
    assert printer.upload(gcode) == "a.gcode"
    assert seen[0].headers["X-Api-Key"] == "KEY"
    assert b'name="print"\r\n\r\ntrue' in seen[0].content
    st = printer.status()
    assert (st.state, st.file, st.progress) == ("Printing", "a.gcode", 42.0)


def test_moonraker_status():
    def handler(request):
        return httpx.Response(200, json={"result": {"status": {
            "print_stats": {"state": "printing", "filename": "x.gcode"}, "display_status": {"progress": 0.5}}}})

    client = httpx.Client(base_url="http://m", transport=httpx.MockTransport(handler))
    st = MoonrakerPrinter("http://m", client=client).status()
    assert (st.state, st.progress) == ("printing", 50.0)


class FakeAnalyzer:
    def __init__(self, spec):
        self.spec = spec
        self.calls = []

    def analyze(self, files, notes, source_type, mode):
        self.calls.append(("analyze", [Path(f).name for f in files], notes))
        return self.spec

    def refine(self, spec, instruction, files):
        self.calls.append(("refine", instruction))
        data = json.loads(spec.model_dump_json())
        data["parts"][0]["primitives"][0]["size_x"] = 100
        return MockupSpec.model_validate(data)


def test_server_flow(tmp_path, monkeypatch):
    from mockup3d import jobs, server

    monkeypatch.setattr(jobs, "DATA_DIR", tmp_path)
    fake = FakeAnalyzer(MockupSpec.model_validate_json(EXAMPLE.read_text()))
    monkeypatch.setattr(server, "analyzer", lambda: fake)
    api = TestClient(server.app)

    r = api.post("/api/jobs", files={"files": ("도면 1.png", b"\x89PNG", "image/png")},
                 data={"notes": "폭 80mm"})
    assert r.status_code == 200, r.text
    job = r.json()
    assert job["report"]["ok"] and "model.stl" in job["files"]
    assert fake.calls[0] == ("analyze", ["도면_1.png"], "폭 80mm")

    r = api.post(f"/api/jobs/{job['id']}/refine", json={"instruction": "폭 100mm"})
    assert r.json()["version"] == 2
    assert r.json()["report"]["size_mm"][0] == 100

    stl = api.get(f"/api/jobs/{job['id']}/files/model.stl")
    assert stl.status_code == 200 and len(stl.content) > 84
    assert api.get("/api/jobs/../../etc").status_code in (400, 404)
    assert api.post(f"/api/jobs/{job['id']}/print", json={}).status_code == 503  # 프린터 미설정


def test_analyzer_builds_request_with_numeral_rules(tmp_path):
    from mockup3d.analyzer import SYSTEM_PROMPT, Analyzer

    captured = {}
    spec = MockupSpec.model_validate_json(EXAMPLE.read_text())

    def parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(stop_reason="end_turn", parsed_output=spec)

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(parse=parse)))
    img = tmp_path / "fig1.png"
    img.write_bytes(b"\x89PNG")
    pdf = tmp_path / "patent.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    out = Analyzer(client=client).analyze([img, pdf], notes="부호 110 = 받침판")
    assert out == spec
    content = captured["messages"][0]["content"]
    assert [b["type"] for b in content] == ["image", "document", "text"]
    assert captured["output_format"] is MockupSpec
    assert "부호" in SYSTEM_PROMPT and "치수가 아닙니다" in SYSTEM_PROMPT
    with pytest.raises(ValueError):
        Analyzer(client=client).analyze([tmp_path / "x.dwg"])
