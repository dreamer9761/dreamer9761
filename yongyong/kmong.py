"""사파리에 띄워 둔 크몽 상담창을 읽는다 (화면에 보이는 글자를 읽기만 하고, 클릭·전송은 하지 않음)."""
import difflib
import re
import subprocess

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
