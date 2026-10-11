#!/usr/bin/env python3
"""이메일 백업 색인·검색 (맥미니 안에서만, 표준 라이브러리, 읽기 전용).
네이버 메일에서 내려받은 메일(.eml), NAS 백업(.eml/.mbox/애플 메일 .emlx)을 읽어 data/mail.db 에 검색용 색인을 만든다.
  python3 mailindex.py build 폴더 [폴더 ...]     색인 만들기 (새로 생기거나 바뀐 파일만)
  python3 mailindex.py search 검색어 [개수]       제목·보낸사람·받는사람·본문·첨부 이름에서 찾기 (예: "블루키워즈", "쿠팡 소명")
  python3 mailindex.py from 주소또는이름 [개수]   특정 사람과 주고받은 메일
  python3 mailindex.py show 번호                  메일 한 통 전체 보기
  python3 mailindex.py stats                     색인 현황"""
import email
import html
import mailbox
import re
import sqlite3
import sys
from email import policy
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path

DB = Path(__file__).resolve().parent / "data" / "mail.db"
MAIL_EXT = {".eml", ".emlx", ".mbox", ".mbx"}


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
    for folder in folders:
        for path in Path(folder).expanduser().rglob("*"):
            if path.suffix.lower() not in MAIL_EXT or not path.is_file() or path.name.startswith("."):
                continue
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
    elif cmd == "show" and a[1:]:
        show(int(a[1].lstrip("#")))
    elif cmd == "stats":
        stats()
    else:
        print(__doc__)
