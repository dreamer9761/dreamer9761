#!/usr/bin/env python3
"""워드·엑셀·파워포인트 파일의 글자 읽기 (표준 라이브러리만, 읽기 전용).
  python3 docread.py 파일.docx [파일2.xlsx ...]"""
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def docx(z):
    out = []
    for name in ["word/document.xml"] + sorted(n for n in z.namelist() if re.match(r"word/(header|footer)\d*\.xml", n)):
        if name in z.namelist():
            root = ET.fromstring(z.read(name))
            for p in root.iter(W + "p"):
                line = "".join(t.text or "" for t in p.iter(W + "t"))
                if line.strip():
                    out.append(line)
    return "\n".join(out)


def xlsx(z):
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        shared = ["".join(t.text or "" for t in si.iter(S + "t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(S + "si")]
    out = []
    for name in sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n)):
        out.append("[%s]" % name.split("/")[-1])
        for row in ET.fromstring(z.read(name)).iter(S + "row"):
            cells = []
            for c in row.iter(S + "c"):
                v = c.find(S + "v")
                text = (v.text or "") if v is not None else "".join(t.text or "" for t in c.iter(S + "t"))
                if c.get("t") == "s" and text.isdigit() and int(text) < len(shared):
                    text = shared[int(text)]
                cells.append(text)
            if any(cells):
                out.append("\t".join(cells))
    return "\n".join(out)


def pptx(z):
    out = []
    slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml", n)), key=lambda n: int(re.findall(r"\d+", n)[0]))
    for i, name in enumerate(slides, 1):
        out.append("[슬라이드 %d]" % i)
        root = ET.fromstring(z.read(name))
        for p in root.iter(A + "p"):
            line = "".join(t.text or "" for t in p.iter(A + "t"))
            if line.strip():
                out.append(line)
    return "\n".join(out)


def read(path):
    ext = path.lower().rsplit(".", 1)[-1]
    if ext not in ("docx", "xlsx", "pptx"):
        return "(%s: 이 형식은 docread 로 못 읽어요. PDF·이미지는 Read 로, 예전 .doc/.hwp 는 PDF 로 바꿔 주세요)" % path
    try:
        with zipfile.ZipFile(path) as z:
            return {"docx": docx, "xlsx": xlsx, "pptx": pptx}[ext](z)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        return "(%s: 읽지 못했어요 - %s)" % (path, e)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for f in sys.argv[1:]:
        print("===== %s =====\n%s\n" % (f, read(f)[:60000]))
