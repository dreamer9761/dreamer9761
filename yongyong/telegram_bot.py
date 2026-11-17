#!/usr/bin/env python3
"""텔레그램으로 용용이와 대화하기. 맥미니가 텔레그램에 새 메시지를 물어 가져오는 방식이라 따로 문을 열 필요가 없다.
봇 토큰은 맥 키체인(yongyong-telegram)에만, 등록한 사람 목록은 data/telegram.json 에 둔다.
등록 코드를 /start 코드 로 보낸 사람만 용용이를 쓸 수 있다.
  python3 telegram_bot.py setup     봇 토큰 넣기 (처음 한 번) → 등록 코드 안내
  python3 telegram_bot.py code      등록 코드 다시 보기 (새로 만들기)
  python3 telegram_bot.py users     등록된 사람 보기
  python3 telegram_bot.py remove 번호   등록 취소"""
import getpass
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

CONF = Path(__file__).resolve().parent / "data" / "telegram.json"
SERVICE = "yongyong-telegram"
TOKEN_RE = re.compile(r"\d{5,}:[A-Za-z0-9_-]{30,}")
MAX_LEN = 4000  # 텔레그램 한 메시지 최대 4096자


def token():
    out = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", "bot", "-w"],
                         capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else ""


def conf():
    try:
        return json.loads(CONF.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"allowed": {}, "code": ""}


_lock = threading.Lock()


def save_conf(c):
    """반쯤 쓴 파일을 다른 메시지가 읽지 않도록, 임시 파일에 다 쓴 뒤 한 번에 바꾼다."""
    with _lock:
        CONF.parent.mkdir(exist_ok=True)
        tmp = CONF.with_suffix(".tmp")
        tmp.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.chmod(0o600)
        os.replace(tmp, CONF)


def api(method, tok=None, timeout=60, **params):
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok or token()}/{method}",
                                 data=json.dumps(params).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        res = json.loads(r.read())
    if not res.get("ok"):
        raise RuntimeError(res.get("description", "텔레그램 오류"))
    return res["result"]


def api_poll(tok, offset):
    """getUpdates 롱 폴링: 새 메시지가 올 때까지 최대 50초 기다린다."""
    params = {"timeout": 50, "allowed_updates": ["message"]}
    if offset is not None:
        params["offset"] = offset
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/getUpdates", data=json.dumps(params).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=70) as r:
        res = json.loads(r.read())
    if not res.get("ok"):
        raise RuntimeError(res.get("description", "텔레그램 오류"))
    return res["result"]


def send(chat_id, text):
    text = str(text).strip() or "…"
    for i in range(0, len(text), MAX_LEN):
        try:
            api("sendMessage", chat_id=chat_id, text=text[i:i + MAX_LEN])
        except Exception as e:
            print(f"(텔레그램 보내기 실패) {e}", flush=True)


def typing(chat_id):
    try:
        api("sendChatAction", chat_id=chat_id, action="typing", timeout=10)
    except Exception:
        pass


def send_file(chat_id, path, caption=""):
    """파일 보내기 (multipart). 50MB 넘으면 텔레그램이 받지 않는다."""
    path = Path(path)
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in (("chat_id", str(chat_id)), ("caption", caption[:1000])):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{path.name}"\r\n'
                 f"Content-Type: application/octet-stream\r\n\r\n".encode() + path.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(f"https://api.telegram.org/bot{token()}/sendDocument", data=b"".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        urllib.request.urlopen(req, timeout=120).read()
    except Exception as e:
        send(chat_id, f"파일을 보내지 못했어요 ({path.name}): {e}")


def download(file_id):
    """보내 준 사진·파일 내려받기 → (파일 이름, 바이트)."""
    info = api("getFile", file_id=file_id)
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{token()}/{info['file_path']}", timeout=120) as r:
        return Path(info["file_path"]).name, r.read()


def new_code():
    c = conf()
    c["code"] = f"{secrets.randbelow(10**6):06d}"
    save_conf(c)
    return c["code"]


def poll(on_message, log=print):
    """새 메시지를 계속 가져와서, 등록된 사람의 메시지만 on_message(msg, user) 로 넘긴다."""
    offset, warned = None, set()
    while True:
        tok = token()
        if not tok:
            time.sleep(300)
            continue
        try:
            updates = api_poll(tok, offset)
        except (urllib.error.URLError, TimeoutError, RuntimeError, OSError) as e:
            log(f"(텔레그램 연결 실패, 1분 뒤 다시) {e}")
            time.sleep(60)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            msg = u.get("message") or {}
            sender = msg.get("from") or {}
            uid, chat = str(sender.get("id", "")), msg.get("chat", {}).get("id")
            if not uid or not chat or msg.get("chat", {}).get("type") != "private":
                continue  # 단체방은 받지 않음 (개인 대화만)
            c = conf()
            text = (msg.get("text") or msg.get("caption") or "").strip()
            if uid not in c["allowed"]:
                m = re.fullmatch(r"/start\s+(\d{6})", text)
                if m and c.get("code") and m.group(1) == c["code"]:
                    name = " ".join(filter(None, [sender.get("last_name"), sender.get("first_name")])) or sender.get("username", "")
                    c["allowed"][uid] = {"name": name, "staff": ""}
                    c["code"] = ""  # 코드는 한 번만 쓸 수 있음
                    save_conf(c)
                    log(f"📱 텔레그램 등록: {name} ({uid})")
                    send(chat, f"반가워요, {name}님! 용용이예요 🐉 이제 여기서 물어보시면 대답할게요.\n"
                               "직원이시면 먼저 '난 ○○○이야' 라고 알려 주세요 (연차 확인용).")
                elif uid not in warned:
                    warned.add(uid)
                    log(f"📱 텔레그램: 등록 안 된 사람의 메시지는 무시했어요 ({uid})")
                    send(chat, "등록되지 않은 사용자예요. 대표님께 등록 코드를 받아서 '/start 코드' 로 보내 주세요.")
                continue
            on_message(msg, c["allowed"][uid] | {"id": uid})


_edit = threading.Lock()  # 읽고-고치고-저장하는 동안 다른 쪽이 끼어들지 않게


def remember_staff(uid, name):
    """'난 김하진이야' 라고 한 텔레그램 사용자는 그 직원으로 기억 (다음부터 '내 연차' 가 바로 됨)."""
    with _edit:
        c = conf()
        if uid in c["allowed"] and c["allowed"][uid].get("staff") != name:
            c["allowed"][uid]["staff"] = name
            save_conf(c)


def setup():
    print("1) 텔레그램에서 @BotFather 를 찾아 대화 → /newbot → 봇 이름(예: 용용이) → 아이디(예: yongyong_robo_bot)")
    print("2) BotFather 가 준 토큰(숫자:영문 긴 글자)을 복사해서 아래에 붙여 넣으세요 (화면에 안 보이는 게 정상).")
    tok = getpass.getpass("   토큰: ").strip()
    if not TOKEN_RE.fullmatch(tok):
        sys.exit("토큰 모양이 아니에요. BotFather 가 준 '123456789:ABC...' 전체를 붙여 넣어 주세요.")
    try:
        me = api("getMe", tok, timeout=20)
    except Exception as e:
        sys.exit(f"텔레그램이 이 토큰을 받지 않아요: {e}")
    # 토큰을 명령줄에 드러내지 않도록 security 의 입력으로 넘긴다
    out = subprocess.run(["security", "-i"], input=f"add-generic-password -U -s {SERVICE} -a bot -w {tok}\n",
                         capture_output=True, text=True)
    if out.returncode != 0 or "error" in (out.stdout + out.stderr).lower():
        sys.exit("맥 키체인에 저장하지 못했어요.")
    code = new_code()
    print(f"\n✅ 연결됐어요: @{me['username']}")
    print(f"3) 휴대폰 텔레그램에서 https://t.me/{me['username']} 를 열고 아래를 그대로 보내세요:")
    print(f"      /start {code}")
    print("   (코드는 한 사람만 한 번 쓸 수 있어요. 직원을 더 등록하려면: ./telegram.sh code)")
    print("4) 용용이를 다시 켜면 (./run.sh) 텔레그램 메시지에 대답하기 시작해요.")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["setup"]:
        setup()
    elif a[:1] == ["code"]:
        print(f"이 코드를 등록할 사람이 봇에게 보내면 돼요:  /start {new_code()}   (한 번만 쓸 수 있어요)")
    elif a[:1] == ["users"]:
        for uid, u in conf()["allowed"].items():
            print(f"{uid}  {u['name']}  {('(직원: ' + u['staff'] + ')') if u.get('staff') else ''}")
    elif a[:1] == ["remove"] and len(a) == 2:
        c = conf()
        print("등록을 취소했어요." if c["allowed"].pop(a[1], None) else "그 번호가 없어요.")
        save_conf(c)
    else:
        print(__doc__)
