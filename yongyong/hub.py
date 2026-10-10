#!/usr/bin/env python3
"""셀러닥터 허브(hub.sellerdoctorai.com) 읽기: 대표님 사파리에 로그인된 허브에서 고객의 결제 금액·계정 현황을 확인한다.
  python3 hub.py links [주소]        페이지의 메뉴·링크 목록 (주소 생략하면 허브 첫 화면)
  python3 hub.py read 주소           페이지 글자 읽기
  python3 hub.py search 검색어 [주소]  페이지의 검색 칸에 검색어를 넣고 결과 읽기 (예: 크몽 닉네임, 계정 번호)
  python3 hub.py pages 주소 [쪽수]    목록을 다음 페이지로 넘기며 읽기
읽기 전용: 검색 칸 입력 말고는 아무것도 누르거나 바꾸지 않는다."""
import json
import sys
import time

from kmong import (_CLOSE_WINDOW, _JS_LINKS, _JS_TEXT, _NEW_WINDOW, _RUN_JS, MAX_CHARS, SafariError, _osa, _wait,
                   read_pages)

BASE = "https://hub.sellerdoctorai.com/"

_JS_SEARCH = r"""((q) => {
  const vis = (e) => e.offsetParent !== null && !e.disabled && !e.readOnly;
  const inputs = Array.from(document.querySelectorAll('input[type=search], input[type=text], input:not([type])')).filter(vis);
  const hint = (e) => [e.placeholder, e.name, e.id, e.getAttribute('aria-label')].join(' ');
  const el = inputs.find(e => /search|검색|query|keyword|고객|이름|닉네임|아이디|계정/i.test(hint(e))) || inputs[0];
  if (!el) return 'noinput';
  el.focus();
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, q);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  for (const type of ['keydown', 'keypress', 'keyup'])
    el.dispatchEvent(new KeyboardEvent(type, { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
  if (el.form) { el.form.requestSubmit ? el.form.requestSubmit() : el.form.submit(); }
  return 'searched:' + hint(el).trim().slice(0, 40);
})(%s)"""


def _url(u):
    u = u if u.startswith("http") else BASE + u.lstrip("/")
    if "sellerdoctorai.com" not in u:
        raise SafariError("허브(sellerdoctorai.com) 주소만 열 수 있어요.")
    return u


def _session(url, steps):
    """새 사파리 창에서 url 을 열고 steps(win) 를 실행한 뒤 창을 닫는다."""
    win = _osa(_NEW_WINDOW, _url(url))
    try:
        _wait(win, 20, lambda ready, logged_in, host: True)
        time.sleep(1.5)
        return steps(win)
    finally:
        try:
            _osa(_CLOSE_WINDOW, win)
        except SafariError:
            pass


def _note_login(text):
    if "로그인" in text[:400] and "로그아웃" not in text:
        return "[주의] 허브에 로그인되어 있지 않은 것 같아요. 사파리에서 hub.sellerdoctorai.com 에 로그인해 주세요.\n" + text
    return text


def read(url):
    return _note_login(_session(url, lambda w: _osa(_RUN_JS, w, _JS_TEXT))[:MAX_CHARS])


def links(url=BASE):
    return _session(url, lambda w: _osa(_RUN_JS, w, _JS_LINKS.replace("kmong.com", "sellerdoctorai.com")))


def search(query, url=BASE):
    def steps(w):
        before = _osa(_RUN_JS, w, _JS_TEXT)
        r = _osa(_RUN_JS, w, _JS_SEARCH % json.dumps(query))
        if r == "noinput":
            return "[이 페이지에는 검색 칸이 없어요. links 로 고객 검색 화면을 찾아 주소를 넣어 주세요.]\n" + before[:3000]
        for _ in range(15):  # 결과가 바뀔 때까지
            time.sleep(0.7)
            after = _osa(_RUN_JS, w, _JS_TEXT)
            if after != before:
                break
        time.sleep(1)
        return "[검색: %s] (%s)\n%s" % (query, r, _osa(_RUN_JS, w, _JS_TEXT))
    return _note_login(_session(url, steps)[:MAX_CHARS])


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "links":
        print(links(rest[0] if rest else BASE))
    elif cmd == "read" and rest:
        print(read(rest[0]))
    elif cmd == "search" and rest:
        print(search(rest[0], rest[1] if len(rest) > 1 else BASE))
    elif cmd == "pages" and rest:
        print(_note_login(read_pages(_url(rest[0]), int(rest[1]) if len(rest) > 1 else 10)))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SafariError as e:
        print(e)
        sys.exit(1)
