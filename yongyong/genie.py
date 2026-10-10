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

SEARCH = "https://www.genie.co.kr/search/searchSong?query="  # '곡' 탭만 (통합 검색은 뮤직비디오·유튜브 영상이 섞여 있음)

# 검색 결과에서 첫 곡의 제목·가수를 읽고 '듣기(재생)' 버튼을 누른다
_JS_PLAY_FIRST = r"""(() => {
  const loggedOut = Array.from(document.querySelectorAll('a,button')).some(e => (e.innerText || '').trim() === '로그인');
  const video = (e) => /youtube|youtu\.be|mv|video|영상|뮤비|뮤직비디오/i.test(
    [e.className, e.getAttribute('href'), e.getAttribute('onclick'), e.title, e.innerText].join(' '));
  // 곡 목록의 줄(tr[songid])만, 뮤직비디오 줄은 제외
  const rows = Array.from(document.querySelectorAll('tr[songid], li[songid], div[songid]'))
    .filter(r => !/youtube|mv|video/i.test(r.className + ' ' + (r.getAttribute('onclick') || '')));
  const row = rows[0];
  if (!row) return JSON.stringify({ ok: false, why: 'notfound', loggedOut });
  const pick = (sel) => { const e = row.querySelector(sel); return e ? e.innerText.trim().replace(/\s+/g, ' ') : ''; };
  const title = pick('.title, a.title') || row.innerText.trim().split('\n')[0];
  const artist = pick('.artist, a.artist');
  const cands = Array.from(row.querySelectorAll('a,button')).filter(e => !video(e));
  const btn = cands.find(e => /btn-listen|fnPlaySong|playSong/i.test(e.className + ' ' + (e.getAttribute('onclick') || '')))
           || cands.find(e => /^(듣기|재생)$/.test((e.innerText || e.title || '').trim()) || e.title === '재생');
  if (btn) btn.click();
  return JSON.stringify({ ok: !!btn, why: btn ? '' : 'nobutton', title, artist, songid: row.getAttribute('songid'), loggedOut,
                          clicked: btn ? (btn.className + ' ' + (btn.getAttribute('onclick') || '')).slice(0, 80) : '' });
})()"""

# 재생 버튼을 눌렀더니 유튜브가 열린 경우 그 탭만 닫기 위해, 누르기 전·후 유튜브 탭을 비교
_YOUTUBE_TABS = r"""
set out to ""
tell application "Safari"
  repeat with w in (every window)
    repeat with t in (every tab of w)
      if URL of t contains "youtube.com" then set out to out & (id of w) & ":" & (index of t) & ":" & (URL of t) & linefeed
    end repeat
  end repeat
end tell
return out
"""
_CLOSE_TAB = r"""
on run argv
  tell application "Safari" to close tab ((item 2 of argv) as integer) of window id ((item 1 of argv) as integer)
end run
"""

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
        before = set(_osa(_YOUTUBE_TABS).splitlines())
        r = json.loads(_osa(_RUN_JS, win, _JS_PLAY_FIRST))
        time.sleep(3)  # 플레이어 창이 뜰 시간
        opened = [t for t in _osa(_YOUTUBE_TABS).splitlines() if t and t not in before]
        for t in reversed(opened):  # 지니 대신 유튜브가 열렸으면 닫음
            w, i, _ = t.split(":", 2)
            _osa(_CLOSE_TAB, w, i)
        if opened:
            r = dict(r, ok=False, why="youtube")
    finally:
        try:
            _osa(_CLOSE_WINDOW, win)
        except SafariError:
            pass
    if r.get("why") == "notfound":
        return "지니에서 '%s'을(를) 찾지 못했어요." % query
    song = " - ".join(x for x in (r.get("artist"), r.get("title")) if x)
    if r.get("why") == "youtube":
        return "'%s'을(를) 누르니 지니 대신 유튜브가 열려서 닫았어요. 지니 검색 화면을 캡처해서 보내 주세요. (누른 버튼: %s)" % (song, r.get("clicked"))
    if not r.get("ok"):
        return "'%s'은(는) 찾았는데 재생 버튼을 누르지 못했어요." % song
    msg = "지니에서 %s 재생을 시작했어요." % song
    if r.get("loggedOut"):
        msg += " (지니에 로그인이 안 돼 있어서 미리듣기만 나올 수 있어요. 사파리에서 지니에 로그인해 주세요.)"
    msg += (" 플레이어 창이 안 뜨거나 소리가 안 나면 사파리 설정 → 웹 사이트에서 genie.co.kr 의 "
            "'팝업 윈도우'를 허용, '자동 재생'을 '모든 미디어 자동 재생 허용'으로 바꿔 주세요.")
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
