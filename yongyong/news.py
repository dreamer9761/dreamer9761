#!/usr/bin/env python3
"""오늘의 뉴스: python3 news.py [주제 또는 검색어]
Google 뉴스 RSS(무료, 가입·키 필요 없음)에서 한국어 기사 제목을 가져온다.
주제: 주요(기본), 경제, IT, 과학, 세계, 국내, 연예, 스포츠, 건강 / 그 밖의 말은 검색어로 사용 (예: 로봇, 3D프린터).
macOS 기본 python3 에서도 돌도록 표준 라이브러리만 사용."""
import datetime
import email.utils
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET

BASE = "https://news.google.com/rss"
LANG = "hl=ko&gl=KR&ceid=KR:ko"
TOPICS = {
    "경제": "BUSINESS", "비즈니스": "BUSINESS", "IT": "TECHNOLOGY", "기술": "TECHNOLOGY", "테크": "TECHNOLOGY",
    "과학": "SCIENCE", "세계": "WORLD", "국제": "WORLD", "해외": "WORLD", "국내": "NATION", "사회": "NATION",
    "정치": "NATION", "연예": "ENTERTAINMENT", "스포츠": "SPORTS", "건강": "HEALTH",
}
HEADLINE_WORDS = ("", "주요", "오늘", "헤드라인", "전체", "뉴스", "주요뉴스", "오늘의뉴스")


def feed_url(topic):
    key = topic.replace(" ", "")
    if key in HEADLINE_WORDS:
        return "주요 뉴스", "%s?%s" % (BASE, LANG)
    for word, code in TOPICS.items():
        if key.upper() == word.upper() or key.replace("뉴스", "") == word:
            return word + " 뉴스", "%s/headlines/section/topic/%s?%s" % (BASE, code, LANG)
    return "'%s' 뉴스" % topic, "%s/search?q=%s+when:1d&%s" % (BASE, urllib.parse.quote(topic), LANG)


def ago(when):
    mins = int((datetime.datetime.now(datetime.timezone.utc) - when).total_seconds() // 60)
    if mins < 60:
        return "%d분 전" % max(mins, 1)
    if mins < 60 * 24:
        return "%d시간 전" % (mins // 60)
    return "%d일 전" % (mins // 1440)


def fetch_news(topic="", limit=12):
    """[{title, source, link, ago}] 와 제목을 돌려준다."""
    label, url = feed_url(topic)
    out = subprocess.run(["curl", "-fsSL", "--max-time", "15", url], capture_output=True)
    if out.returncode != 0:
        raise RuntimeError("뉴스 서버에 연결하지 못했어요: " + out.stderr.decode(errors="ignore").strip())
    items, seen = [], set()
    for it in ET.fromstring(out.stdout).iter("item"):
        title = (it.findtext("title") or "").strip()
        source = (it.findtext("source") or "").strip()
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        key = title.replace(" ", "")[:20]
        if not title or key in seen:
            continue
        seen.add(key)
        when = ""
        try:
            when = ago(email.utils.parsedate_to_datetime(it.findtext("pubDate")))
        except (TypeError, ValueError):
            pass
        items.append({"title": title, "source": source, "link": it.findtext("link") or "", "ago": when})
        if len(items) >= limit:
            break
    return label, items


def main():
    topic = " ".join(sys.argv[1:]).strip()
    label, items = fetch_news(topic)
    print("[%s] %s 기준 (Google 뉴스)" % (label, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    if not items:
        print("관련 기사가 없어요.")
    for i, n in enumerate(items, 1):
        print("%d. %s (%s%s)" % (i, n["title"], n["source"] or "출처 미상", ", " + n["ago"] if n["ago"] else ""))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ET.ParseError) as e:
        print(e)
        sys.exit(1)
