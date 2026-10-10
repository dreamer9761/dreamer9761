"""사파리에 띄워 둔 크몽 상담창을 읽는다 (화면에 보이는 글자를 읽기만 하고, 클릭·전송은 하지 않음)."""
import difflib
import os
import re
import subprocess
import tempfile

MAX_CHARS = 30000

# 사파리에서 kmong.com 탭을 모두 찾아 "URL\n본문" 으로 돌려준다. 탭 사이는 \x1e 로 구분.
_SCRIPT = r'''
set out to ""
tell application "Safari"
  repeat with w in windows
    repeat with t in tabs of w
      if URL of t contains "kmong.com" then
        set pageText to do JavaScript "document.body.innerText" in t
        set out to out & (URL of t) & linefeed & pageText & (character id 30)
      end if
    end repeat
  end repeat
end tell
return out
'''

# 시간이 지나면 저절로 바뀌는 표시("3분 전" 등)는 변화 감지에서 제외
_VOLATILE = re.compile(r"방금\s*전|\d+\s*(초|분|시간|일)\s*전|\d{1,2}:\d{2}")


class SafariError(RuntimeError):
    pass


def read_pages():
    """크몽 탭들의 [(url, text)]. 메시지/상담 탭을 앞에 둔다."""
    p = subprocess.run(["osascript", "-e", _SCRIPT], capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        err = p.stderr.strip()
        if "JavaScript" in err or "Apple Events" in err or "Apple 이벤트" in err:
            raise SafariError("사파리에서 'Apple Events의 JavaScript 허용'을 켜 주세요.")
        raise SafariError(f"사파리를 읽지 못했어요: {err}")
    pages = []
    for chunk in p.stdout.split("\x1e"):
        if chunk.strip():
            url, _, text = chunk.strip().partition("\n")
            pages.append((url, text.strip()))
    pages.sort(key=lambda pt: not re.search(r"inbox|message|chat", pt[0]))
    return pages


def snapshot():
    """모든 크몽 탭 내용을 한 덩어리 글로 (너무 길면 자름). 크몽 탭이 없으면 빈 문자열."""
    text = "\n\n".join(f"[탭] {url}\n{body}" for url, body in read_pages())
    return text[:MAX_CHARS]


def fingerprint(text):
    return _VOLATILE.sub("", text)


def changes(old, new):
    """이전 화면과 비교해 새로 생긴 줄만."""
    diff = difflib.ndiff(fingerprint(old).splitlines(), fingerprint(new).splitlines())
    return "\n".join(line[2:] for line in diff if line.startswith("+ ") and line[2:].strip())


# ── 크몽 페이지를 열어 읽기 (용용이/Claude 가 실행하는 명령) ─────────────────────
# 대표님 사파리에 이미 로그인된 크몽을 그대로 사용한다. 새 탭으로 열어 글자만 읽고 탭을 닫는다 (클릭·입력 없음).
_OPEN_AND_READ = r'''
on run argv
  set theURL to item 1 of argv
  set js to item 2 of argv
  tell application "Safari"
    if (count of windows) = 0 then make new document
    set w to front window
    set keep to current tab of w
    set t to make new tab at end of tabs of w with properties {URL:theURL}
    set current tab of w to keep
    set lastLen to -1
    repeat 30 times
      delay 0.7
      try
        set n to do JavaScript "document.readyState == 'complete' ? document.body.innerText.length : -1" in t
        if n > 200 and n = lastLen then exit repeat
        set lastLen to n
      end try
    end repeat
    set pageText to do JavaScript js in t
    set finalURL to URL of t
    close t
  end tell
  return finalURL & linefeed & pageText
end run
'''

_JS_TEXT = "document.body.innerText"
_JS_LINKS = r"""Array.from(new Set(Array.from(document.querySelectorAll('a[href]'))
  .map(a => (a.innerText || a.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 60) + ' | ' + a.href)
  .filter(s => s.includes('kmong.com') && !s.startsWith(' |')))).join('\n')"""


def open_and_read(url, js=_JS_TEXT):
    if not url.startswith("http"):
        url = "https://kmong.com/" + url.lstrip("/")
    with tempfile.NamedTemporaryFile("w", suffix=".applescript", delete=False) as f:
        f.write(_OPEN_AND_READ)
    try:
        p = subprocess.run(["osascript", f.name, url, js], capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(f.name)
    if p.returncode != 0:
        err = p.stderr.strip()
        if "JavaScript" in err or "Apple Events" in err or "Apple 이벤트" in err:
            raise SafariError("사파리에서 'Apple Events의 JavaScript 허용'을 켜 주세요.")
        raise SafariError("사파리로 크몽을 열지 못했어요: " + err)
    final, _, body = p.stdout.partition("\n")
    if "login" in final or ("로그인" in body[:300] and "로그아웃" not in body):
        body = "[주의] 크몽에 로그인되어 있지 않은 것 같아요. 사파리에서 크몽에 로그인해 주세요.\n" + body
    return final, body.strip()[:MAX_CHARS]


def _cli(argv):
    usage = ("사용법:\n  python3 kmong.py links [주소]   크몽 페이지의 링크(메뉴) 목록\n"
             "  python3 kmong.py read 주소      크몽 페이지 글자 읽기\n"
             "  python3 kmong.py current        지금 사파리에 열린 크몽 탭 읽기")
    if not argv:
        print(usage)
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "current":
        print(snapshot() or "사파리에 크몽 탭이 없어요.")
    elif cmd == "links":
        final, body = open_and_read(rest[0] if rest else "https://kmong.com/", _JS_LINKS)
        print("[링크 목록] " + final + "\n" + body)
    elif cmd == "read" and rest:
        final, body = open_and_read(rest[0])
        print("[페이지] " + final + "\n" + body)
    else:
        print(usage)
        return 1
    return 0


if __name__ == "__main__":
    import sys
    try:
        sys.exit(_cli(sys.argv[1:]))
    except (SafariError, subprocess.TimeoutExpired) as e:
        print(e)
        sys.exit(1)
