"""사파리에 띄워 둔 크몽 상담창을 읽는다 (화면에 보이는 글자를 읽기만 하고, 클릭·전송은 하지 않음)."""
import difflib
import os
from pathlib import Path
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


# ── 크몽 자동 로그인 (소셜 로그인 + 전문가 모드 전환) ───────────────────────────
# 비밀번호는 다루지 않는다. 사파리에 남아 있는 카카오·네이버·구글·애플 로그인 상태로 버튼만 눌러 다시 로그인한다.
PROVIDERS = {
    "카카오": ["카카오", "kakao"], "네이버": ["네이버", "naver"],
    "구글": ["구글", "google"], "애플": ["애플", "apple"],
}
_NEW_WINDOW = r"""
on run argv
  tell application "Safari"
    make new document with properties {URL:(item 1 of argv)}
    return id of front window
  end tell
end run
"""
_RUN_JS = r"""
on run argv
  tell application "Safari" to return do JavaScript (item 2 of argv) in current tab of window id ((item 1 of argv) as integer)
end run
"""
_CLOSE_WINDOW = r"""
on run argv
  tell application "Safari" to close window id ((item 1 of argv) as integer)
end run
"""
_JS_STATE = r"""(() => {
  const texts = Array.from(document.querySelectorAll('a,button')).map(e => (e.innerText || '').trim());
  const out = texts.some(t => t === '로그인' || t === '회원가입');
  return (document.readyState === 'complete' ? 'ready' : 'loading') + '|' + (out ? 'out' : 'in') + '|' + location.host;
})()"""
_JS_CLICK = r"""((want, avoid) => {
  const norm = (e) => (e.innerText || e.getAttribute('aria-label') || e.getAttribute('alt') || e.title || '').replace(/\s+/g, '').toLowerCase();
  const els = Array.from(document.querySelectorAll('a,button,[role=button],img[alt]'));
  const el = els.find(e => { const t = norm(e); return t && want.some(w => t.includes(w)) && !avoid.some(a => t.includes(a)); });
  if (!el) return 'notfound';
  (el.closest('a,button,[role=button]') || el).click();
  return 'clicked:' + norm(el).slice(0, 30);
})(%s, %s)"""


def _osa(script, *args):
    with tempfile.NamedTemporaryFile("w", suffix=".applescript", delete=False) as f:
        f.write(script)
    try:
        p = subprocess.run(["osascript", f.name, *map(str, args)], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(f.name)
    if p.returncode != 0:
        err = p.stderr.strip()
        if "JavaScript" in err or "Apple Events" in err or "Apple 이벤트" in err:
            raise SafariError("사파리에서 'Apple Events의 JavaScript 허용'을 켜 주세요.")
        raise SafariError(err)
    return p.stdout.strip()


def _click(win, want, avoid=()):
    import json
    return _osa(_RUN_JS, win, _JS_CLICK % (json.dumps([w.lower() for w in want]), json.dumps([a.lower() for a in avoid])))


def _state(win):
    try:
        ready, login, host = _osa(_RUN_JS, win, _JS_STATE).split("|")
        return ready == "ready", login == "in", host
    except (SafariError, ValueError):
        return False, False, ""


def _wait(win, seconds, done):
    import time
    for _ in range(int(seconds / 0.7)):
        time.sleep(0.7)
        st = _state(win)
        if st[0] and done(*st):
            return True
    return False


def login(provider):
    """크몽에 소셜 로그인 후 전문가 모드로 전환. 결과 문장을 돌려준다."""
    import time
    words = PROVIDERS.get(provider.replace("로그인", "").strip())
    if not words:
        return "로그인 방법을 카카오, 네이버, 구글, 애플 중에서 알려 주세요."
    win = _osa(_NEW_WINDOW, "https://kmong.com/")
    _wait(win, 20, lambda ready, logged_in, host: True)
    if not _state(win)[1]:
        _click(win, ["로그인"], ["로그인없이"])
        _wait(win, 15, lambda ready, logged_in, host: True)
        time.sleep(1.5)
        if _click(win, words) == "notfound":
            return "크몽 로그인 화면에서 %s 버튼을 찾지 못했어요. 열린 사파리 창에서 직접 로그인해 주세요." % provider
        # 카카오 등의 로그인이 사파리에 남아 있으면 바로 돌아오고, 아니면 대표님이 창에서 직접 로그인할 때까지 기다림
        if not _wait(win, 120, lambda ready, logged_in, host: "kmong.com" in host and logged_in):
            return "%s 로그인이 끝나지 않았어요. 열린 사파리 창에서 직접 로그인해 주세요." % provider
    time.sleep(1.5)
    switched = _click(win, ["전문가로전환", "전문가전환", "전문가모드"], ["구매자"])
    if switched != "notfound":
        _wait(win, 15, lambda ready, logged_in, host: True)
    _osa(_CLOSE_WINDOW, win)
    return "크몽에 로그인했어요" + (" (전문가 모드로 전환)" if switched != "notfound" else "") + "."


_JS_NEXT_PAGE = r"""(() => {
  // 페이지 번호 목록에서 '지금 페이지 + 1' 을 누르고, 없으면 '다음' 화살표를 누른다
  const vis = (e) => e.offsetParent !== null && !e.disabled && e.getAttribute('aria-disabled') !== 'true';
  const press = (e) => (e.querySelector('a,button,[role=button]') || e.closest('a,button,[role=button]') || e).click();
  const els = Array.from(document.querySelectorAll('a,button,[role=button],li')).filter(vis);
  const num = (e) => (e.innerText || '').trim();
  const cur = els.find(e => /^\d+$/.test(num(e)) && (e.getAttribute('aria-current') || /active|current|selected/i.test(e.className)));
  if (cur) {
    const want = String(Number(num(cur)) + 1);
    const nx = els.find(e => num(e) === want && e !== cur);
    if (nx) { press(nx); return 'page:' + want; }
  }
  const arrow = els.find(e => {
    const t = (num(e) + ' ' + (e.getAttribute('aria-label') || '') + ' ' + (e.title || '')).toLowerCase();
    return /^(다음|다음 페이지|next|›|»|>)$/.test(num(e)) || /다음\s*페이지|next\s*page/.test(t);
  });
  if (arrow) { press(arrow); return 'next'; }
  return 'end';
})()"""


def read_list_pages(url, max_pages=10):
    """목록 페이지를 열고 '다음 페이지'를 눌러 가며 max_pages 쪽까지 글자를 모은다 (월별 매출 계산용)."""
    import time
    if not url.startswith("http"):
        url = "https://kmong.com/" + url.lstrip("/")
    win = _osa(_NEW_WINDOW, url)
    try:
        _wait(win, 20, lambda ready, logged_in, host: True)
        time.sleep(1.5)
        pages, last = [], None
        for n in range(1, max_pages + 1):
            text = _osa(_RUN_JS, win, _JS_TEXT)
            if text == last:
                break
            pages.append("[%d쪽]\n%s" % (n, text[:MAX_CHARS]))
            last = text
            if n == max_pages or _osa(_RUN_JS, win, _JS_NEXT_PAGE) == "end":
                break
            for _ in range(15):  # 내용이 바뀔 때까지 기다림
                time.sleep(0.7)
                if _osa(_RUN_JS, win, _JS_TEXT) != last:
                    break
            time.sleep(0.8)
        return "\n\n".join(pages)
    finally:
        _osa(_CLOSE_WINDOW, win)


# ── 상담 도우미: 지금 열린 크몽 대화창 읽기, 자주 쓰는 문구 읽기, 입력창에 초안 넣기(보내지는 않음) ──
_IN_CHAT_TAB = r"""
on run argv
  tell application "Safari"
    set best to missing value
    repeat with w in (every window)
      repeat with t in (every tab of w)
        set u to URL of t
        if u contains "kmong.com" then
          if best is missing value then set best to t
          if u contains "inbox" or u contains "message" or u contains "chat" then
            set best to t
            exit repeat
          end if
        end if
      end repeat
    end repeat
    if best is missing value then return "nokmong"
    return do JavaScript (item 1 of argv) in best
  end tell
end run
"""
# 대화 내용이 들어 있는(스크롤되는) 가장 큰 영역을 맨 위로 올려 예전 메시지를 불러온다
_JS_CHAT_SCROLL = r"""(() => {
  const boxes = Array.from(document.querySelectorAll('div, section, ul')).filter(e => {
    const s = getComputedStyle(e);
    return /(auto|scroll)/.test(s.overflowY) && e.scrollHeight > e.clientHeight + 50 && e.clientWidth > 300;
  });
  const box = boxes.sort((a, b) => b.clientWidth * b.clientHeight - a.clientWidth * a.clientHeight)[0];
  if (!box) return '0';
  box.setAttribute('data-yongyong-chat', '1');
  box.scrollTop = 0;
  return String(box.scrollHeight);
})()"""
_JS_CHAT_TEXT = r"""(() => {
  const box = document.querySelector('[data-yongyong-chat]');
  return box ? box.innerText : document.body.innerText;
})()"""
# '자주 쓰는 문구' 창: 제목 목록 → 각 문구의 연필(수정) 버튼으로 본문을 열어 읽고, 저장하지 않고 닫는다.
# 휴지통(삭제)·저장·전송 버튼은 절대 누르지 않는다.
_JS_TPL = r"""((cmd, idx) => {
  const vis = (e) => e && e.offsetParent !== null;
  const txt = (e) => (e.innerText || e.value || '').trim();
  const clickable = () => Array.from(document.querySelectorAll('button, a, [role=button]')).filter(vis);
  const addBtn = clickable().find(e => /문구\s*추가/.test(txt(e)));
  // 목록 창: '문구 추가하기' 버튼을 품은 가장 가까운 상자 중 제목 '자주 쓰는 문구' 가 있는 것
  let modal = addBtn;
  while (modal && !(/자주\s*쓰는\s*문구/.test(modal.innerText || '') && modal.querySelectorAll('svg').length >= 4)) modal = modal.parentElement;
  const rows = () => {
    if (!modal) return [];
    const icons = Array.from(modal.querySelectorAll('button, [role=button], a')).filter(e => vis(e) && !txt(e) && e.querySelector('svg, img, i'));
    const out = [];
    for (const b of icons) {
      let row = b.parentElement;
      while (row && row !== modal && !(row.innerText || '').replace(/^\s*\d+\s*/, '').trim()) row = row.parentElement;
      if (row && row !== modal && !out.includes(row)) out.push(row);
    }
    return out.map(r => ({ row: r, title: (r.innerText || '').replace(/^\s*\d+\s*/, '').split('\n').map(s => s.trim()).filter(Boolean)[0] || '',
                          icons: Array.from(r.querySelectorAll('button, [role=button], a')).filter(e => vis(e) && !txt(e) && e.querySelector('svg, img, i')) }));
  };
  if (cmd === 'open') {
    if (modal) return 'already';
    const b = clickable().find(e => /^자주\s*쓰는\s*문구$/.test(txt(e)));
    if (!b) return 'notfound';
    b.click(); return 'opened';
  }
  if (cmd === 'list') return JSON.stringify(rows().map(r => r.title));
  if (cmd === 'edit') {
    const r = rows()[idx];
    if (!r || r.icons.length !== 2) return 'unsure';          // 연필·휴지통 두 개가 아니면 손대지 않음
    window.__yyEditBefore = document.body.innerText.length;
    r.icons[0].click();                                          // 왼쪽 = 연필(수정)
    return 'editing:' + r.title;
  }
  if (cmd === 'read') {
    if (/삭제\s*하시겠|삭제할까요|정말\s*삭제/.test(document.body.innerText)) return 'DANGER';
    const fields = Array.from(document.querySelectorAll('textarea, input[type=text], input:not([type])')).filter(e => vis(e) && e.value && e.value.length > 1);
    return JSON.stringify(fields.map(f => f.value));
  }
  if (cmd === 'cancel') {
    const b = clickable().reverse().find(e => /^(취소|닫기|아니요|아니오)$/.test(txt(e)));
    if (b) { b.click(); return 'closed'; }
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', keyCode: 27, bubbles: true }));
    return 'escaped';
  }
  return 'bad';
})(%s, %d)"""


_JS_INSERT = r"""((text) => {
  const vis = (e) => e.offsetParent !== null && !e.disabled && !e.readOnly;
  const box = Array.from(document.querySelectorAll('textarea, [contenteditable=true]')).filter(vis)
    .sort((a, b) => b.getBoundingClientRect().width - a.getBoundingClientRect().width)[0];
  if (!box) return 'noinput';
  box.focus();
  if (box.tagName === 'TEXTAREA') {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(box, text);
  } else {
    box.innerText = text;
  }
  box.dispatchEvent(new Event('input', { bubbles: true }));
  box.dispatchEvent(new Event('change', { bubbles: true }));
  return 'inserted';
})(%s)"""


def _chat_js(js):
    out = _osa(_IN_CHAT_TAB, js)
    if out == "nokmong":
        raise SafariError("사파리에 크몽 탭이 없어요. 크몽에서 상담할 대화를 열어 주세요.")
    return out


def read_chat():
    """지금 사파리에 열린 크몽 대화를 처음 메시지까지 거슬러 올라가 전부 읽는다."""
    import time
    last = None
    for _ in range(20):
        height = _chat_js(_JS_CHAT_SCROLL)
        if height == last:
            break
        last = height
        time.sleep(1.2)
    return _chat_js(_JS_CHAT_TEXT)[-MAX_CHARS:]


def _tpl(cmd, idx=0):
    import json
    return _chat_js(_JS_TPL % (json.dumps(cmd), idx))


def read_templates(save_to=None):
    """크몽 '자주 쓰는 문구'의 제목과 본문을 모두 읽는다. 각 문구는 수정 창으로 열어 읽고 저장하지 않고 닫는다."""
    import json
    import time
    if _tpl("open") == "notfound":
        return "크몽 대화창에서 '자주 쓰는 문구' 버튼을 찾지 못했어요. 상담 대화를 하나 열어 주세요."
    time.sleep(1.5)
    titles = json.loads(_tpl("list") or "[]")
    if not titles:
        return "자주 쓰는 문구 목록을 읽지 못했어요."
    out = []
    for i, title in enumerate(titles):
        body = ""
        if _tpl("edit", i).startswith("editing"):
            time.sleep(1.2)
            got = _tpl("read")
            if got == "DANGER":  # 혹시 삭제 확인 창이면 바로 취소하고 멈춤
                _tpl("cancel")
                out.append("### %s\n(본문을 읽다가 멈췄어요)" % title)
                break
            values = [v for v in json.loads(got or "[]") if v.strip() != title.strip()]
            body = max(values, key=len) if values else ""
            _tpl("cancel")
            time.sleep(1)
            if _tpl("open") == "opened":  # 수정 창을 닫으며 목록도 닫혔으면 다시 열기
                time.sleep(1.2)
        out.append("### %d. %s\n%s" % (i + 1, title, body or "(본문을 읽지 못했어요)"))
    _tpl("cancel")  # 목록 창 닫기
    text = "# 크몽 자주 쓰는 문구 (%s 읽음)\n\n" % time.strftime("%Y-%m-%d %H:%M") + "\n\n".join(out) + "\n"
    if save_to:
        Path(save_to).write_text(text, encoding="utf-8")
    return text


_JS_OPEN_CHAT = r"""((name) => {
  // 메시지 목록에서 닉네임이 한 줄로 딱 맞는 대화를 찾아 연다 (클릭은 대화 열기만)
  const norm = (t) => (t || '').replace(/\s+/g, '');
  const cand = Array.from(document.querySelectorAll('a, li, [role=button], div')).filter(e =>
    e.offsetParent !== null && (e.innerText || '').split('\n').some(l => norm(l) === norm(name)) && e.innerText.length < 400);
  const el = cand.sort((a, b) => a.innerText.length - b.innerText.length)[0];
  if (!el) return 'notfound';
  (el.closest('a, li, [role=button]') || el).click();
  return 'opened';
})(%s)"""


def open_chat(nickname):
    """크몽 메시지 탭에서 해당 손님 대화를 연다."""
    import json
    import time
    if _chat_js(_JS_OPEN_CHAT % json.dumps(nickname)) != "opened":
        return False
    time.sleep(2.5)
    return True


def insert_draft(text):
    """크몽 대화 입력창에 초안을 넣기만 한다. 보내기는 대표님이 직접."""
    import json
    return _chat_js(_JS_INSERT % json.dumps(text)) == "inserted"


def _cli(argv):
    usage = ("사용법:\n  python3 kmong.py links [주소]   크몽 페이지의 링크(메뉴) 목록\n"
             "  python3 kmong.py read 주소      크몽 페이지 글자 읽기\n"
             "  python3 kmong.py current        지금 사파리에 열린 크몽 탭 읽기\n"
             "  python3 kmong.py pages 주소 [쪽수]  목록을 다음 페이지로 넘기며 읽기 (기본 10쪽, 월별 매출 계산용)\n"
             "  python3 kmong.py login 카카오   크몽 자동 로그인 + 전문가 모드 (카카오/네이버/구글/애플)\n"
             "  python3 kmong.py chat           지금 열린 크몽 대화를 처음부터 전부 읽기\n"
             "  python3 kmong.py templates      대화창의 '자주 쓰는 문구' 목록 읽기")
    if not argv:
        print(usage)
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "current":
        print(snapshot() or "사파리에 크몽 탭이 없어요.")
    elif cmd == "links":
        final, body = open_and_read(rest[0] if rest else "https://kmong.com/", _JS_LINKS)
        print("[링크 목록] " + final + "\n" + body)
    elif cmd == "pages" and rest:
        print(read_list_pages(rest[0], int(rest[1]) if len(rest) > 1 else 10))
    elif cmd == "chat":
        print("[대화 전체]\n" + read_chat())
    elif cmd == "templates":
        print(read_templates(Path(__file__).resolve().parent / "data" / "kmong_templates.md"))
    elif cmd == "login" and rest:
        print(login(rest[0]))
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
