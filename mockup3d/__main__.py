"""CLI.

  python -m mockup3d analyze 도면.pdf 사진.jpg --notes "전체 폭 120mm" -o out/
  python -m mockup3d build examples/phone_stand.json -o out/
  python -m mockup3d serve
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import geometry, printability
from .spec import MockupSpec


def _emit(spec: MockupSpec, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "spec.json").write_text(spec.model_dump_json(indent=2))
    report = printability.check(spec)
    files = geometry.export(spec, out) if report.size_mm != [0, 0, 0] else {}
    (out / "report.json").write_text(report.model_dump_json(indent=2))
    print(json.dumps({"files": [str(p) for p in files.values()], "report": report.model_dump()},
                     ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="mockup3d")
    sub = parser.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="사진/도면 → AI 사양 → STL")
    a.add_argument("files", nargs="+")
    a.add_argument("--notes", default="")
    a.add_argument("--mode", choices=["appearance", "functional"], default="appearance")
    a.add_argument("-o", "--out", default="out")

    b = sub.add_parser("build", help="사양 JSON → STL (AI 호출 없음)")
    b.add_argument("spec")
    b.add_argument("-o", "--out", default="out")

    s = sub.add_parser("serve", help="웹 UI 실행")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    if args.cmd == "analyze":
        from .analyzer import Analyzer

        _emit(Analyzer().analyze(args.files, args.notes, mode=args.mode), Path(args.out))
    elif args.cmd == "build":
        _emit(MockupSpec.model_validate_json(Path(args.spec).read_text()), Path(args.out))
    else:
        import uvicorn

        uvicorn.run("mockup3d.server:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
