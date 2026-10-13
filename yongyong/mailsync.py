#!/usr/bin/env python3
"""네이버 메일 연동 (IMAP, 읽기 전용): 메일함의 새 메일을 가져와 data/mail.db 검색 색인에 넣는다.
메일을 지우거나, 읽음 표시하거나, 보내지 않는다. 비밀번호는 맥 키체인(yongyong-naver-mail)에만 있다.
  python3 mailsync.py test 아이디      로그인되는지 확인
  python3 mailsync.py sync 아이디      새 메일 가져오기 (처음엔 전체, 다음부터는 새 메일만)"""
import base64
import email
import imaplib
import os
import re
import subprocess
import sys
from email import policy

import mailindex

HOST = "imap.naver.com"
SERVICE = "yongyong-naver-mail"
SKIP = re.compile(r"휴지통|스팸|Deleted|Trash|Junk|Spam|임시보관|Drafts", re.I)
BATCH = 40
MAX_BYTES = 3_000_000  # 한 통에서 앞부분 3MB 만 (큰 첨부는 잘라도 본문은 앞에 있음)


def password(user):
    if os.environ.get("YONGYONG_NAVER_TEST_PW"):  # 대화창에서 새 비밀번호를 저장하기 전에 먼저 확인할 때만
        return os.environ["YONGYONG_NAVER_TEST_PW"]
    out = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", user, "-w"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("키체인에 네이버 메일 비밀번호가 없어요. ./naver_mail_setup.sh 를 먼저 실행해 주세요.")
    return out.stdout.strip()


def connect(user):
    con = imaplib.IMAP4_SSL(HOST, 993, timeout=60)
    try:
        con.login(user.split("@")[0], password(user))
    except imaplib.IMAP4.error as e:
        print("(로그인 실패 이유: %s)" % e, flush=True)
        print("네이버 메일에 로그인이 안 돼서 자동 연동을 멈췄어요. 로그인 실패가 쌓이면 네이버가 ID 보호조치를 하니, "
              "새 애플리케이션 비밀번호로 naver_mail_setup.sh 를 다시 실행해 주세요.")
        sys.exit(2)  # 2 = 로그인 거절: 용용이가 자동 재시도를 멈춤
    return con


def utf7_decode(name):
    """IMAP 메일함 이름(수정된 UTF-7, 예: &vPSwuNO4ycDVaA-) → 한글."""
    def dec(m):
        s = m.group(1)
        if not s:
            return "&"
        s = s.replace(",", "/")
        return base64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-16-be", errors="replace")
    return re.sub(r"&([^-]*)-", dec, name)


def mailboxes(con):
    boxes = []
    for line in con.list()[1] or []:
        line = line.decode(errors="replace") if isinstance(line, bytes) else str(line)
        m = re.match(r'\((?P<flags>[^)]*)\) (?:"[^"]*"|NIL) (?P<name>.+)$', line)
        if not m or "\\Noselect" in m["flags"] or re.search(r"\\(Trash|Junk|Drafts)", m["flags"]):
            continue
        raw = m["name"].strip().strip('"')
        if not SKIP.search(utf7_decode(raw)):
            boxes.append(raw)
    return boxes


def sync(user):
    imap, con = connect(user), mailindex.db()
    con.execute("CREATE TABLE IF NOT EXISTS imap_sync (mailbox TEXT PRIMARY KEY, validity INTEGER, last_uid INTEGER)")
    seen_ids = {r[0] for r in con.execute("SELECT msgid FROM mail WHERE msgid != ''")}
    plan = []  # (메일함, 한글 이름, 가져올 UID 목록, uidvalidity)
    for raw in mailboxes(imap):
        name = utf7_decode(raw)
        typ, _ = imap.select('"%s"' % raw, readonly=True)  # 읽기 전용: 읽음 표시가 바뀌지 않음
        if typ != "OK":
            continue
        validity = int((imap.response("UIDVALIDITY")[1] or [b"0"])[0])
        row = con.execute("SELECT validity, last_uid FROM imap_sync WHERE mailbox = ?", (raw,)).fetchone()
        last = row[1] if row and row[0] == validity else 0
        if row and row[0] != validity:  # 메일함이 새로 만들어졌으면 처음부터 다시
            con.execute("DELETE FROM mail WHERE path LIKE ?", ("naver:%s/%%" % name,))
        uids = [int(u) for u in (imap.uid("search", None, "UID %d:*" % (last + 1))[1][0] or b"").split()]
        uids = [u for u in uids if u > last]
        plan.append((raw, name, uids, validity))
    total = sum(len(p[2]) for p in plan) or 1
    done = added = 0
    print("PROGRESS 0 0", flush=True)
    for raw, name, uids, validity in plan:
        imap.select('"%s"' % raw, readonly=True)
        for i in range(0, len(uids), BATCH):
            batch = uids[i:i + BATCH]
            typ, data = imap.uid("fetch", ",".join(map(str, batch)), "(BODY.PEEK[]<0.%d>)" % MAX_BYTES)
            for item in data if typ == "OK" else []:
                if not isinstance(item, tuple):
                    continue
                m = re.search(rb"UID (\d+)", item[0])
                try:
                    msg = email.message_from_bytes(item[1], policy=policy.default)
                    r = mailindex.row_of(msg, "naver:%s/%s" % (name, m.group(1).decode() if m else "?"))
                except Exception as e:  # 깨진 메일은 건너뜀
                    print("(건너뜀) %s: %s" % (name, e))
                    continue
                if r[7] and r[7] in seen_ids:  # 내려받은 백업에 이미 있는 메일
                    continue
                seen_ids.add(r[7])
                con.execute("INSERT INTO mail VALUES (?,?,?,?,?,?,?,?)", r)
                added += 1
            done += len(batch)
            con.execute("INSERT OR REPLACE INTO imap_sync VALUES (?, ?, ?)", (raw, validity, batch[-1]))
            con.commit()
            print("PROGRESS %d %d" % (min(99, done * 100 // total), added), flush=True)
    con.commit()
    imap.logout()
    all_mail = con.execute("SELECT count(*) FROM mail").fetchone()[0]
    print("네이버 메일 연동 완료: 새 메일 %d통을 가져왔어요. 색인에 모두 %d통이 있어요." % (added, all_mail))


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "test":
        c = connect(a[1])
        print("로그인 성공! 메일함: " + ", ".join(utf7_decode(b) for b in mailboxes(c)))
        c.logout()
    elif len(a) == 2 and a[0] == "sync":
        sync(a[1])
    else:
        print(__doc__)
