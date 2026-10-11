#!/usr/bin/env python3
"""이메일 백업 색인·검색 (맥미니 안에서만, 표준 라이브러리, 읽기 전용).
네이버 메일에서 내려받은 메일(.eml), NAS 백업(.eml/.mbox/애플 메일 .emlx)을 읽어 data/mail.db 에 검색용 색인을 만든다.
  python3 mailindex.py build 폴더 [폴더 ...]     색인 만들기 (새로 생기거나 바뀐 파일만)
  python3 mailindex.py search 검색어 [개수]       제목·보낸사람·받는사람·본문·첨부 이름에서 찾기 (예: "블루키워즈", "쿠팡 소명")
  python3 mailindex.py from 주소또는이름 [개수]   특정 사람과 주고받은 메일
  python3 mailindex.py customer 계정번호 회사명 닉네임 ...   크몽 고객 한 명의 메일 기록 한꺼번에 (최근 순, 보냄/받음 표시)
  python3 mailindex.py show 번호                  메일 한 통 전체 보기
  python3 mailindex.py stats                     색인 현황"""
import email
import html
import mailbox
import re
import sqlite3
import sys
import zipfile
from email import policy
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path

DB = Path(__file__).resolve().parent / "data" / "mail.db"
MAIL_EXT = {".eml", ".emlx", ".mbox", ".mbx", ".zip"}  # .zip 은 안에 든 .eml 을 풀지 않고 바로 읽음


def db():
    DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, mtime REAL)")
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS mail USING fts5(date, sender, recipients, subject, body, attachments, path UNINDEXED, msgid UNINDEXED, tokenize='unicode61')")
    return con


def text_of(msg):
    """본문 글자 (텍스트 우선, 없으면 HTML 에서 태그 제거) 와 첨부 이름들."""
    plain, htm, files = [], [], []
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.is_multipart():
            continue
        name = part.get_filename()
        if name or part.get_content_disposition() == "attachment":
            files.append(str(name or "첨부"))
            continue
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        try:
            payload = part.get_content()
        except (LookupError, ValueError, AssertionError):
            raw = part.get_payload(decode=True) or b""
            payload = raw.decode(part.get_content_charset() or "utf-8", errors="replace")
        (plain if ctype == "text/plain" else htm).append(str(payload))
    body = "\n".join(plain)
    if not body.strip() and htm:
        body = re.sub(r"(?is)<(script|style).*?</\1>", " ", "\n".join(htm))
        body = html.unescape(re.sub(r"(?s)<[^>]+>", " ", body))
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", body)).strip()[:20000], ", ".join(files)


def row_of(msg, path):
    def h(name):
        try:
            return str(msg.get(name, "") or "")
        except Exception:
            return ""
    try:
        date = parsedate_to_datetime(h("Date")).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        date = ""
    addrs = lambda field: ", ".join(f"{n} <{a}>" if n else a for n, a in getaddresses([h(field)]))  # noqa: E731
    body, files = text_of(msg)
    return (date, addrs("From"), ", ".join(filter(None, [addrs("To"), addrs("Cc")])), h("Subject"), body, files,
            str(path), h("Message-ID"))


def messages(path):
    ext = path.suffix.lower()
    if ext == ".zip":  # 네이버 메일 백업은 zip 으로 받아지는 경우가 많음
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if info.filename.lower().endswith(".eml") and not info.is_dir():
                    yield email.message_from_bytes(z.read(info), policy=policy.default)
        return
    if ext in (".mbox", ".mbx"):
        for m in mailbox.mbox(str(path), factory=lambda f: email.message_from_binary_file(f, policy=policy.default)):
            yield m
    else:
        raw = path.read_bytes()
        if ext == ".emlx":  # 애플 메일: 첫 줄은 바이트 수
            first, _, rest = raw.partition(b"\n")
            raw = rest[: int(first.strip() or 0)] if first.strip().isdigit() else rest
        yield email.message_from_bytes(raw, policy=policy.default)


def build(folders):
    con, added, files = db(), 0, 0
    seen_ids = {r[0] for r in con.execute("SELECT msgid FROM mail WHERE msgid != ''")}
    paths = [path for folder in folders for path in Path(folder).expanduser().rglob("*")
             if path.suffix.lower() in MAIL_EXT and not path.name.startswith(".") and path.is_file()]
    sizes = [path.stat().st_size for path in paths]
    total_bytes, done_bytes, shown = max(sum(sizes), 1), 0, None

    def progress(extra=0):  # 용용이가 캐릭터 위 말풍선에 % 로 보여 줌 (파일 크기 기준)
        nonlocal shown
        pct = min(99, (done_bytes + extra) * 100 // total_bytes)
        if (pct, added // 500) != shown:
            shown = (pct, added // 500)
            print("PROGRESS %d %d" % (pct, added), flush=True)

    for path, size in zip(paths, sizes):
        progress()
        done_bytes += size
        mtime = path.stat().st_mtime
        old = con.execute("SELECT mtime FROM files WHERE path = ?", (str(path),)).fetchone()
        if old and old[0] == mtime:
            continue
        con.execute("DELETE FROM mail WHERE path = ?", (str(path),))
        try:
            for msg in messages(path):
                r = row_of(msg, path)
                if r[7] and r[7] in seen_ids:  # 같은 메일이 여러 백업에 있으면 한 번만
                    continue
                seen_ids.add(r[7])
                con.execute("INSERT INTO mail VALUES (?,?,?,?,?,?,?,?)", r)
                added += 1
                if added % 500 == 0:
                    progress(-size // 2)  # 큰 백업 파일 하나를 오래 읽을 때도 메일 수가 올라가게
        except Exception as e:  # 깨진 파일은 건너뜀
            print("(건너뜀) %s: %s" % (path, e))
        con.execute("INSERT OR REPLACE INTO files VALUES (?, ?)", (str(path), mtime))
        files += 1
        if files % 200 == 0:
            con.commit()
            print("... 파일 %d개, 메일 %d통" % (files, added), flush=True)
    con.commit()
    total = con.execute("SELECT count(*) FROM mail").fetchone()[0]
    print("색인 완료: 새로 읽은 파일 %d개, 추가된 메일 %d통, 전체 %d통" % (files, added, total))


def show_rows(rows):
    for rid, date, sender, rcpt, subject, snip in rows:
        print("#%d | %s | 보낸: %s | 받은: %s | %s\n    %s" % (rid, date, sender[:60], rcpt[:60], subject, snip.replace("\n", " ")))
    if not rows:
        print("찾은 메일이 없어요.")


def search(q, n=20):
    con = db()
    terms = " ".join('"%s"' % t.replace('"', "") for t in q.split())
    try:
        rows = con.execute("SELECT rowid, date, sender, recipients, subject, snippet(mail, 4, '[', ']', '…', 12) FROM mail "
                           "WHERE mail MATCH ? ORDER BY date DESC LIMIT ?", (terms, n)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    if not rows:  # 한글 일부만 맞는 경우(예: 회사명 일부)는 LIKE 로 한 번 더
        like = "%" + q + "%"
        rows = con.execute("SELECT rowid, date, sender, recipients, subject, substr(body, 1, 120) FROM mail WHERE subject LIKE ? "
                           "OR sender LIKE ? OR recipients LIKE ? OR body LIKE ? OR attachments LIKE ? ORDER BY date DESC LIMIT ?",
                           (like, like, like, like, like, n)).fetchall()
    show_rows(rows)


def by_person(who, n=30):
    like = "%" + who + "%"
    show_rows(db().execute("SELECT rowid, date, sender, recipients, subject, substr(body, 1, 120) FROM mail "
                           "WHERE sender LIKE ? OR recipients LIKE ? ORDER BY date DESC LIMIT ?", (like, like, n)).fetchall())


ADDR = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def customer(keys, n=15):
    """크몽 고객 한 명의 메일 기록을 한꺼번에: 계정 번호·회사명·닉네임·이메일 중 하나라도 들어간 메일을 모으고,
    그 메일에 나온 고객 이메일 주소로 한 번 더 찾아서(회사명을 안 쓴 메일까지) 최근 순으로 보여 준다."""
    con = db()
    count = {}  # 우리 주소 = 거의 모든 메일(보낸·받은)에 들어 있는 주소
    for sender, rcpt in con.execute("SELECT sender, recipients FROM mail ORDER BY date DESC LIMIT 3000"):
        for a in set(ADDR.findall(((sender or "") + " " + (rcpt or "")).lower())):
            count[a] = count.get(a, 0) + 1
    top = max(count.values(), default=0)
    ours = {a for a, c in count.items() if c >= top * 0.3}
    found = {}

    def add(sql, args):
        for r in con.execute(sql, args).fetchall():
            found[r[0]] = r

    cols = "rowid, date, sender, recipients, subject, body, attachments"
    for k in [k for k in keys if len(k.strip()) >= 2]:
        try:
            add("SELECT %s FROM mail WHERE mail MATCH ? LIMIT 200" % cols, ('"%s"' % k.replace('"', ""),))
        except sqlite3.OperationalError:
            pass
        like = "%" + k + "%"
        add("SELECT %s FROM mail WHERE subject LIKE ? OR sender LIKE ? OR recipients LIKE ? OR attachments LIKE ? LIMIT 200" % cols,
            (like,) * 4)
    addrs = {}
    for r in found.values():
        for a in ADDR.findall((r[2] or "") + " " + (r[3] or "")):
            if a.lower() not in ours:
                addrs[a] = addrs.get(a, 0) + 1
    for a, _ in sorted(addrs.items(), key=lambda x: -x[1])[:3]:  # 고객 주소로 한 번 더
        add("SELECT %s FROM mail WHERE sender LIKE ? OR recipients LIKE ? LIMIT 200" % cols, ("%" + a + "%",) * 2)
    rows = sorted(found.values(), key=lambda r: r[1] or "", reverse=True)
    if not rows:
        print("이 고객과 주고받은 메일이 색인에 없어요. (찾은 말: %s)" % ", ".join(keys))
        return
    print("메일 %d통 (%s ~ %s) / 고객 주소: %s" % (len(rows), rows[-1][1] or "-", rows[0][1] or "-",
                                                ", ".join(sorted(addrs, key=lambda a: -addrs[a])[:3]) or "-"))
    for i, (rid, date, sender, rcpt, subject, body, files) in enumerate(rows[:n]):
        way = "보냄" if any(o in (sender or "").lower() for o in ours) else "받음"
        text = re.sub(r"\s+", " ", body or "")[: 600 if i < 3 else 150]  # 최근 3통은 길게
        print("#%d | %s | %s | %s%s\n    %s" % (rid, date, way, subject, " | 첨부: " + files[:80] if files else "", text))


def show(rid):
    r = db().execute("SELECT date, sender, recipients, subject, attachments, body, path FROM mail WHERE rowid = ?", (rid,)).fetchone()
    if not r:
        print("그 번호의 메일이 없어요.")
        return
    print("날짜: %s\n보낸 사람: %s\n받는 사람: %s\n제목: %s\n첨부: %s\n파일: %s\n\n%s" % (r[0], r[1], r[2], r[3], r[4] or "-", r[6], r[5]))


def stats():
    con = db()
    total, first, last = con.execute("SELECT count(*), min(date), max(date) FROM mail").fetchone()
    files = con.execute("SELECT count(*) FROM files").fetchone()[0]
    print("메일 %d통 (%s ~ %s), 백업 파일 %d개" % (total, first or "-", last or "-", files))


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else ""
    if cmd == "build" and a[1:]:
        build(a[1:])
    elif cmd == "search" and a[1:]:
        search(" ".join(x for x in a[1:] if not x.isdigit()) or a[1], int(a[-1]) if a[-1].isdigit() and len(a) > 2 else 20)
    elif cmd == "from" and a[1:]:
        by_person(a[1], int(a[2]) if len(a) > 2 else 30)
    elif cmd == "customer" and a[1:]:
        customer(a[1:])
    elif cmd == "show" and a[1:]:
        show(int(a[1].lstrip("#")))
    elif cmd == "stats":
        stats()
    else:
        print(__doc__)
