"""밖(사무실·휴대폰)에서 용용이 화면에 들어올 때 쓰는 아이디·비밀번호 로그인.
맥미니 안(사파리)에서 여는 건 로그인 없이, Tailscale 등으로 들어오는 요청은 로그인한 기기만 받는다.
비밀번호는 원문을 저장하지 않고 PBKDF2 해시만 data/remote.json 에 둔다."""
import hashlib
import hmac
import json
import secrets
import threading
import time
from pathlib import Path

CONFIG = Path(__file__).resolve().parent / "data" / "remote.json"
TOKEN_DAYS = 30
_lock = threading.Lock()
_fails = []  # 최근 로그인 실패 시각 (무작위 대입 막기)


def _load():
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {}


def _save(conf):
    CONFIG.parent.mkdir(exist_ok=True)
    CONFIG.write_text(json.dumps(conf))
    CONFIG.chmod(0o600)


def _hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()


def enabled():
    return bool(_load().get("id"))


def set_account(user, pw):
    salt = secrets.token_hex(16)
    _save({"id": user, "salt": salt, "hash": _hash(pw, salt), "tokens": {}})


def login(user, pw):
    """맞으면 새 토큰, 아니면 None. 10분에 5번 넘게 틀리면 잠시 막는다."""
    with _lock:
        now = time.time()
        _fails[:] = [t for t in _fails if now - t < 600]
        if len(_fails) >= 5:
            return None
        conf = _load()
        ok = conf.get("id") and hmac.compare_digest(str(user), conf["id"]) and \
            hmac.compare_digest(_hash(str(pw), conf["salt"]), conf["hash"])
        if not ok:
            _fails.append(now)
            return None
        token = secrets.token_urlsafe(32)
        tokens = {k: v for k, v in conf.get("tokens", {}).items() if v > now}
        tokens[hashlib.sha256(token.encode()).hexdigest()] = now + TOKEN_DAYS * 86400
        conf["tokens"] = tokens
        _save(conf)
        return token


def locked():
    now = time.time()
    return len([t for t in _fails if now - t < 600]) >= 5


def valid(token):
    if not token:
        return False
    exp = _load().get("tokens", {}).get(hashlib.sha256(token.encode()).hexdigest())
    return bool(exp and exp > time.time())


def logout(token):
    conf = _load()
    conf.get("tokens", {}).pop(hashlib.sha256((token or "").encode()).hexdigest(), None)
    _save(conf)


if __name__ == "__main__":  # remote_setup.sh 에서 호출: 아이디·비밀번호 정하기
    import getpass
    user = input("아이디: ").strip()
    pw = getpass.getpass("비밀번호 (8자 이상, 입력해도 안 보여요): ")
    if len(user) < 2 or len(pw) < 8 or pw != getpass.getpass("비밀번호 한 번 더: "):
        raise SystemExit("아이디는 2자 이상, 비밀번호는 8자 이상이고 두 번 같아야 해요.")
    set_account(user, pw)
    print("저장했어요.")
