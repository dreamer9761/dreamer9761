#!/usr/bin/env python3
"""텔레그램으로 용용이와 대화하기. 맥미니가 텔레그램에 새 메시지를 물어 가져오는 방식이라 따로 문을 열 필요가 없다.
봇 토큰은 맥 키체인(yongyong-telegram)에만, 등록한 사람 목록은 data/telegram.json 에 둔다.
등록 코드를 /start 코드 로 보낸 사람만 용용이를 쓸 수 있다.
  python3 telegram_bot.py setup     봇 토큰 넣기 (처음 한 번) → 등록 코드 안내
  python3 telegram_bot.py code      등록 코드 다시 보기 (새로 만들기)
  python3 telegram_bot.py users     등록된 사람 보기
  python3 telegram_bot.py call 비서야 비서   단체방에서 부르는 말 바꾸기 (기존 봇과 겹칠 때)
  python3 telegram_bot.py check     안 될 때 점검
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


def send(chat_id, text, reply_to=None):
    """보내기 (단체방에서는 물어본 메시지에 답장으로 달아 누구 질문의 대답인지 보이게)."""
    text = str(text).strip() or "…"
    for i in range(0, len(text), MAX_LEN):
        params = {"chat_id": chat_id, "text": text[i:i + MAX_LEN]}
        if reply_to and i == 0:
            params["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
        try:
            api("sendMessage", **params)
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
        except urllib.error.HTTPError as e:
            if e.code == 409:  # 다른 프로그램이 같은 봇으로 메시지를 받고 있음
                log("⚠️ 텔레그램: 다른 프로그램(웹훅이나 다른 봇 프로그램)이 같은 봇을 쓰고 있어서 메시지를 못 받아요. "
                    "./telegram.sh setup 을 다시 실행하거나 그 프로그램을 꺼 주세요. (5분 뒤 다시)")
                time.sleep(300)
            else:
                log(f"(텔레그램 연결 실패 {e.code}, 1분 뒤 다시)")
                time.sleep(60)
            continue
        except (urllib.error.URLError, TimeoutError, RuntimeError, OSError) as e:
            log(f"(텔레그램 연결 실패, 1분 뒤 다시) {e}")
            time.sleep(60)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            try:
                _handle_update(u, on_message, log, warned)
            except Exception as e:  # 메시지 하나 때문에 텔레그램 전체가 멈추지 않게
                log(f"(텔레그램 메시지 처리 오류) {e}")


DEFAULT_CALL = ["용용아", "용용이야", "용용이", "용용"]  # 단체방에서 부르는 말 (./telegram.sh call 로 바꿀 수 있음)
_me = {}


def bot_username():
    if not _me.get("username"):
        try:
            _me.update(api("getMe", timeout=20))
        except Exception:
            return ""
    return _me.get("username", "")


def _name(sender):
    return " ".join(filter(None, [sender.get("last_name"), sender.get("first_name")])) or sender.get("username", "")


def _handle_update(u, on_message, log, warned):
    msg = u.get("message") or {}
    sender, chat_info = msg.get("from") or {}, msg.get("chat") or {}
    uid, chat, kind = str(sender.get("id", "")), chat_info.get("id"), chat_info.get("type")
    if not uid or not chat or sender.get("is_bot"):
        return
    text = (msg.get("text") or msg.get("caption") or "").strip()
    c = conf()
    start = re.fullmatch(r"/start(?:@\w+)?\s+(\d{6})", text)
    code_ok = bool(start and c.get("code") and start.group(1) == c["code"])

    if kind in ("group", "supergroup"):
        gid = str(chat)
        if gid not in c.setdefault("groups", {}):
            if code_ok:  # 단체방 등록: 방에서 '/start@봇아이디 코드'
                with _edit:
                    c = conf()
                    c.setdefault("groups", {})[gid] = {"title": chat_info.get("title", "")}
                    c["code"] = ""
                    save_conf(c)
                log(f"📱 텔레그램 단체방 등록: {chat_info.get('title')} ({gid})")
                send(chat, f"안녕하세요, 용용이예요 🐉 이 방에서는 '{(c.get('call_words') or DEFAULT_CALL)[0]} ...' 로 시작하거나 저를 @멘션하거나 "
                           "제 메시지에 답장하시면 대답할게요.")
            elif gid not in warned:
                warned.add(gid)
                log(f"📱 텔레그램: 등록 안 된 단체방은 무시했어요 ({chat_info.get('title')})")
            return
        # 등록된 단체방: 불렀을 때만 대답 (용용아 / @봇 멘션 / 용용이 메시지에 답장)
        me = bot_username()
        mention = f"@{me}" if me else None
        replied = ((msg.get("reply_to_message") or {}).get("from") or {}).get("username") == me and me
        words = sorted(c.get("call_words") or DEFAULT_CALL, key=len, reverse=True)  # 긴 말부터 ("용용이야" 가 "용용" 보다 먼저)
        call_re = r"^\s*(" + "|".join(map(re.escape, words)) + r")(?=$|[\s,!?.~])[,\s!?.~]*"
        called = re.match(call_re, text) or (mention and mention.lower() in text.lower())
        if not (called or replied):
            return
        text = re.sub(call_re, "", text)
        if mention:
            text = re.sub(re.escape(mention), "", text, flags=re.I).strip()
        msg = dict(msg, text=text, caption=None)
        user = {"id": uid, "name": _name(sender), "staff": c.get("staff", {}).get(uid, ""),
                "reply_to": msg.get("message_id"), "group": chat_info.get("title", "")}
        on_message(msg, user)
        return

    if kind != "private":
        return
    if uid not in c["allowed"]:
        if code_ok:
            name = _name(sender)
            with _edit:
                c = conf()
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
        return
    user = c["allowed"][uid] | {"id": uid}
    user["staff"] = user.get("staff") or c.get("staff", {}).get(uid, "")
    on_message(msg, user)


_edit = threading.Lock()  # 읽고-고치고-저장하는 동안 다른 쪽이 끼어들지 않게


def remember_staff(uid, name):
    """'난 김하진이야' 라고 한 텔레그램 사용자는 그 직원으로 기억 (다음부터 '내 연차' 가 바로 됨)."""
    with _edit:
        c = conf()
        if c.setdefault("staff", {}).get(uid) != name:  # 개인 대화·단체방 모두 같은 사람으로 기억
            c["staff"][uid] = name
            if uid in c["allowed"]:
                c["allowed"][uid]["staff"] = name
            save_conf(c)


def setup():
    print("1) 이미 만든 봇: 텔레그램 @BotFather → /mybots → 내 봇 선택 → API Token → 토큰 복사")
    print("   (새로 만들 때: @BotFather → /newbot → 봇 이름 → 아이디(…bot 으로 끝남))")
    print("2) 토큰(숫자:영문 긴 글자)을 아래에 붙여 넣으세요 (화면에 안 보이는 게 정상).")
    tok = getpass.getpass("   토큰: ").strip()
    if not TOKEN_RE.fullmatch(tok):
        sys.exit("토큰 모양이 아니에요. BotFather 가 준 '123456789:ABC...' 전체를 붙여 넣어 주세요.")
    try:
        me = api("getMe", tok, timeout=20)
    except Exception as e:
        sys.exit(f"텔레그램이 이 토큰을 받지 않아요: {e}")
    hook = api("getWebhookInfo", tok, timeout=20).get("url")
    if hook:  # 다른 프로그램(웹훅)이 이 봇의 메시지를 받고 있으면 용용이가 받을 수 없음
        print(f"\n⚠️  이 봇은 지금 다른 프로그램(웹훅)으로 메시지가 가고 있어요: {hook.split('?')[0][:60]}")
        print("   용용이가 대답하려면 이 연결을 끊어야 해요. 그 프로그램은 이 봇 메시지를 더 받지 못하게 돼요.")
        if input("   끊고 용용이로 바꿀까요? (y/N) ").strip().lower() != "y":
            sys.exit("바꾸지 않았어요. 용용이 전용 봇을 새로 만들어 쓰는 것도 방법이에요 (@BotFather → /newbot).")
        api("deleteWebhook", tok, timeout=20)
        print("   ✅ 웹훅을 끊었어요.")
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
        code = new_code()
        print(f"개인 등록: 등록할 사람이 봇과의 대화에서  /start {code}")
        print(f"단체방 등록: 봇을 방에 초대한 뒤 방에서  /start@{bot_username() or '봇아이디'} {code}")
        print("(코드는 한 번만 쓸 수 있어요)")
    elif a[:1] == ["check"]:
        ok = lambda t: print("  ✅ " + t)  # noqa: E731
        bad = lambda t: print("  ❌ " + t)  # noqa: E731
        tok = token()
        if not tok:
            bad("봇 토큰이 없어요 → ./telegram.sh setup")
            sys.exit()
        try:
            me = api("getMe", tok, timeout=20)
            ok(f"봇 연결됨: @{me['username']}")
        except Exception as e:
            bad(f"토큰이 안 맞아요 ({e}) → BotFather 에서 /revoke 로 새 토큰을 받아 ./telegram.sh setup")
            sys.exit()
        if me.get("can_read_all_group_messages"):
            ok("단톡방의 일반 메시지를 읽을 수 있음 (privacy 꺼짐)")
        else:
            bad("봇이 단톡방 일반 메시지를 못 읽어요 → BotFather /setprivacy → 봇 선택 → Disable, "
                "그다음 방에서 봇을 내보냈다가 다시 초대 (그전까지는 @멘션·답장만 돼요)")
        hook = api("getWebhookInfo", tok, timeout=20).get("url")
        bad("다른 프로그램(웹훅)이 이 봇 메시지를 가져가고 있어요 → ./telegram.sh setup") if hook else ok("웹훅 없음")
        c = conf()
        groups = c.get("groups", {})
        ok("등록된 단체방: " + ", ".join(g.get("title", gid) for gid, g in groups.items())) if groups else \
            bad("등록된 단체방이 없어요 → ./telegram.sh code 로 받은 '/start@봇아이디 숫자' 를 방에 보내기")
        print("  부르는 말: " + ", ".join(c.get("call_words") or DEFAULT_CALL) + " (또는 @" + me["username"] + ")")
        running = subprocess.run(["pgrep", "-f", "python yongyong.py"], capture_output=True).returncode == 0
        ok("용용이 켜져 있음 (텔레그램 대답은 용용이가 켜져 있어야 해요)") if running else bad("용용이가 꺼져 있어요 → ./run.sh")
    elif a[:1] == ["call"]:
        c = conf()
        if a[1:]:
            c["call_words"] = a[1:]
            save_conf(c)
            print("단체방에서 이렇게 부르면 대답해요: " + ", ".join(a[1:]) + "  (@멘션·답장은 언제나 돼요)")
        else:
            print("지금 부르는 말: " + ", ".join(c.get("call_words") or DEFAULT_CALL)
                  + "\n바꾸기 예: ./telegram.sh call 비서야 비서")
    elif a[:1] == ["users"]:
        for uid, u in conf()["allowed"].items():
            print(f"{uid}  {u['name']}  {('(직원: ' + u['staff'] + ')') if u.get('staff') else ''}")
        for gid, g in conf().get("groups", {}).items():
            print(f"{gid}  [단체방] {g.get('title', '')}")
    elif a[:1] == ["remove"] and len(a) == 2:
        c = conf()
        gone = c["allowed"].pop(a[1], None) or c.setdefault("groups", {}).pop(a[1], None)
        print("등록을 취소했어요." if gone else "그 번호가 없어요.")
        save_conf(c)
    else:
        print(__doc__)
