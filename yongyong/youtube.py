#!/usr/bin/env python3
"""유튜브 음악: 사파리에서 유튜브를 검색해 위에서부터 n개 영상을 하나의 재생목록으로 이어서 튼다.
  python3 youtube.py play 유키구라모토 10 views   조회수 높은 순으로 10개 (views 를 빼면 관련도 순)
  python3 youtube.py stop                          용용이가 연 유튜브 재생목록 끄기
로그인은 필요 없다. 사파리 설정에서 youtube.com 자동 재생을 허용해 두어야 소리가 바로 난다."""
import json
import sys
import time
import urllib.parse

from kmong import _CLOSE_WINDOW, _NEW_WINDOW, _RUN_JS, SafariError, _osa, _wait

SORT_VIEWS = "&sp=CAM%253D"  # 유튜브 검색 '조회수 순' 정렬

# 검색 결과에서 일반 영상(쇼츠·광고 제외)의 id 와 제목을 위에서부터
_JS_RESULTS = r"""((n) => {
  const out = [], seen = new Set();
  for (const a of document.querySelectorAll('a#video-title, a#video-title-link, ytd-video-renderer a[href*="/watch?v="]')) {
    const m = (a.getAttribute('href') || '').match(/[?&]v=([\w-]{11})/);
    if (!m || seen.has(m[1]) || a.closest('ytd-ad-slot-renderer, ytd-reel-shelf-renderer')) continue;
    seen.add(m[1]);
    out.push({ id: m[1], title: (a.getAttribute('title') || a.innerText || '').trim() });
    if (out.length >= n) break;
  }
  return JSON.stringify(out);
})(%d)"""

_JS_STATE = r"""(() => { const v = document.querySelector('video'); return v ? (v.paused ? 'paused' : 'playing') : 'none'; })()"""
_JS_PLAY = r"""(() => {
  const v = document.querySelector('video');
  if (v && v.paused) { const b = document.querySelector('.ytp-play-button'); if (b) b.click(); v.play().catch(() => {}); }
  return v ? 'ok' : 'none';
})()"""

# 용용이가 연 재생목록(watch_videos 로 만든 임시 목록, list=TL...)이 있는 탭에서 실행 / 닫기
_IN_OUR_TAB = r"""
on run argv
  tell application "Safari"
    repeat with w in (every window)
      repeat with t in (every tab of w)
        if URL of t contains "youtube.com/watch" and URL of t contains "list=TL" then
          if (item 1 of argv) is "close" then
            close t
            return "closed"
          end if
          return do JavaScript (item 2 of argv) in t
        end if
      end repeat
    end repeat
  end tell
  return "nowindow"
end run
"""


def search(query, n=10, views=False):
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query) + (SORT_VIEWS if views else "")
    win = _osa(_NEW_WINDOW, url)
    try:
        _wait(win, 20, lambda ready, logged_in, host: True)
        found = []
        for _ in range(10):  # 결과가 그려질 때까지
            time.sleep(1)
            found = json.loads(_osa(_RUN_JS, win, _JS_RESULTS % n) or "[]")
            if len(found) >= min(n, 5):
                break
        return found
    finally:
        try:
            _osa(_CLOSE_WINDOW, win)
        except SafariError:
            pass


def state():
    return _osa(_IN_OUR_TAB, "js", _JS_STATE)


def play(query, n=10, views=False):
    """(성공 여부, 제목 목록, 안내 문장)"""
    videos = search(query, n, views)
    if not videos:
        return False, [], "유튜브에서 '%s'을(를) 찾지 못했어요." % query
    stop()
    ids = ",".join(v["id"] for v in videos)
    _osa(_NEW_WINDOW, "https://www.youtube.com/watch_videos?video_ids=" + ids)
    for _ in range(12):  # 재생목록이 열리고 영상이 시작될 때까지
        time.sleep(1.5)
        st = state()
        if st == "playing":
            break
        if st == "paused":
            _osa(_IN_OUR_TAB, "js", _JS_PLAY)
    titles = [v["title"] for v in videos]
    if state() != "playing":
        return False, titles, ("유튜브 재생목록을 열었는데 사파리가 자동 재생을 막았어요. 유튜브 창에서 Safari → 이 웹 사이트에 대한 설정 → "
                               "자동 재생을 '모든 미디어 자동 재생 허용'으로 바꿔 주세요. 지금은 재생 버튼을 한 번 눌러 주시면 이어서 나와요.")
    sort = "조회수 높은 순으로 " if views else ""
    return True, titles, "유튜브에서 %s%d곡을 이어서 틀어요. 첫 곡은 %s." % (sort, len(titles), titles[0])


def stop():
    n = 0
    while _osa(_IN_OUR_TAB, "close", "") == "closed":
        n += 1
    return "유튜브 음악을 껐어요." if n else "켜져 있는 유튜브 음악이 없어요."


def main(argv):
    if argv[:1] == ["stop"]:
        print(stop())
    elif argv[:1] == ["play"] and len(argv) > 1:
        words = argv[1:]
        views = words[-1] == "views" and bool(words.pop())
        n = int(words.pop()) if len(words) > 1 and words[-1].isdigit() else 10
        print(play(" ".join(words), n, views)[2])
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
