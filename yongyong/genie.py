#!/usr/bin/env python3
"""지니뮤직 재생: 사파리에 로그인된 지니(genie.co.kr)에서 노래를 검색해 첫 곡을 튼다.
  python3 genie.py play 아이유 좋은날     검색해서 첫 곡 재생
  python3 genie.py stop                  지니 플레이어 끄기
  python3 genie.py volume 30             맥 소리 크기(0~100)
지니는 공개 API 가 없어서 대표님 사파리의 지니 웹 플레이어를 대신 눌러 주는 방식이다 (로그인·이용권 필요)."""
import json
import sys
import time
import urllib.parse

from kmong import _CLOSE_WINDOW, _NEW_WINDOW, _RUN_JS, SafariError, _osa, _wait

SEARCH = "https://www.genie.co.kr/search/searchMain?query="

# 검색 결과에서 첫 곡의 제목·가수를 읽고 '듣기(재생)' 버튼을 누른다
_JS_PLAY_FIRST = r"""(() => {
  const loggedOut = Array.from(document.querySelectorAll('a,button')).some(e => (e.innerText || '').trim() === '로그인');
  const row = document.querySelector('tr[songid], [songid], li[songid]');
  if (!row) return JSON.stringify({ ok: false, why: 'notfound', loggedOut });
  const pick = (sel) => { const e = row.querySelector(sel); return e ? e.innerText.trim().replace(/\s+/g, ' ') : ''; };
  const title = pick('.title, .info .title, a.title') || row.innerText.trim().split('\n')[0];
  const artist = pick('.artist, .info .artist, a.artist');
  const btn = Array.from(row.querySelectorAll('a,button')).find(e =>
    /listen|play/i.test(e.className + ' ' + (e.getAttribute('onclick') || '')) || /듣기|재생/.test((e.innerText || '') + (e.title || '')));
  if (btn) btn.click();
  return JSON.stringify({ ok: !!btn, why: btn ? '' : 'nobutton', title, artist, songid: row.getAttribute('songid'), loggedOut });
})()"""

_CLOSE_PLAYERS = r"""
tell application "Safari"
  set n to 0
  repeat with w in (every window)
    repeat with t in (every tab of w)
      if URL of t contains "genie.co.kr/player" then
        close t
        set n to n + 1
      end if
    end repeat
  end repeat
  return n
end tell
"""


def play(query):
    win = _osa(_NEW_WINDOW, SEARCH + urllib.parse.quote(query))
    try:
        _wait(win, 20, lambda ready, logged_in, host: True)
        time.sleep(1.5)
        r = json.loads(_osa(_RUN_JS, win, _JS_PLAY_FIRST))
        time.sleep(3)  # 플레이어 창이 뜰 시간
    finally:
        try:
            _osa(_CLOSE_WINDOW, win)
        except SafariError:
            pass
    if r.get("why") == "notfound":
        return "지니에서 '%s'을(를) 찾지 못했어요." % query
    song = " - ".join(x for x in (r.get("artist"), r.get("title")) if x)
    if not r.get("ok"):
        return "'%s'은(는) 찾았는데 재생 버튼을 누르지 못했어요." % song
    msg = "지니에서 %s 재생을 시작했어요." % song
    if r.get("loggedOut"):
        msg += " (지니에 로그인이 안 돼 있어서 미리듣기만 나올 수 있어요. 사파리에서 지니에 로그인해 주세요.)"
    msg += " 플레이어 창이 안 뜨면 사파리 설정 → 웹 사이트 → 팝업 윈도우에서 genie.co.kr 을 '허용'으로 바꿔 주세요."
    return msg


def stop():
    n = int(_osa(_CLOSE_PLAYERS) or 0)
    return "지니 플레이어를 껐어요." if n else "켜져 있는 지니 플레이어가 없어요."


def volume(level):
    level = max(0, min(100, int(level)))
    _osa('on run argv\nset volume output volume ((item 1 of argv) as integer)\nend run', level)
    return "소리 크기를 %d로 맞췄어요." % level


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd, rest = argv[0], " ".join(argv[1:]).strip()
    if cmd == "play" and rest:
        print(play(rest))
    elif cmd == "stop":
        print(stop())
    elif cmd == "volume" and rest.isdigit():
        print(volume(rest))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (SafariError, ValueError) as e:
        print(e)
        sys.exit(1)
