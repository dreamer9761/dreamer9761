#!/usr/bin/env python3
"""날씨 조회: python3 weather.py 강릉
Open-Meteo(무료, 가입·키 필요 없음)에서 현재·시간별·주간 날씨를 가져와 한국어로 짧게 출력한다.
용용이(Claude)가 날씨 질문을 받으면 이 스크립트를 실행한다. macOS 기본 python3 에서도 돌도록 표준 라이브러리만 사용."""
import json
import subprocess
import sys
import urllib.parse

CITIES = {
    "서울": (37.5665, 126.978), "인천": (37.4563, 126.7052), "수원": (37.2636, 127.0286), "춘천": (37.8813, 127.7298),
    "원주": (37.3422, 127.9202), "강릉": (37.7519, 128.8761), "속초": (38.207, 128.5918), "청주": (36.6424, 127.489),
    "대전": (36.3504, 127.3845), "세종": (36.48, 127.289), "천안": (36.8151, 127.1139), "안동": (36.5684, 128.7294),
    "포항": (36.019, 129.3435), "대구": (35.8714, 128.6014), "울산": (35.5384, 129.3114), "부산": (35.1796, 129.0756),
    "창원": (35.2281, 128.6811), "전주": (35.8242, 127.148), "광주": (35.1595, 126.8526), "목포": (34.8118, 126.3922),
    "여수": (34.7604, 127.6622), "제주": (33.4996, 126.5312), "서귀포": (33.2541, 126.56), "울릉": (37.4845, 130.9057),
}
DAYS = "월화수목금토일"


def sky(code):
    if code == 0: return "맑음"
    if code == 1: return "대체로 맑음"
    if code == 2: return "구름 조금"
    if code == 3: return "흐림"
    if code <= 48: return "안개"
    if code <= 57: return "이슬비"
    if code <= 67: return "비"
    if code <= 77: return "눈"
    if code <= 82: return "소나기"
    if code <= 86: return "눈 소나기"
    return "뇌우"


def fetch(url):
    # macOS 의 curl 은 시스템 인증서를 쓰므로 파이썬 인증서 설정 문제를 피할 수 있다
    out = subprocess.run(["curl", "-fsS", "--max-time", "15", url], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError("날씨 서버에 연결하지 못했어요: " + out.stderr.strip())
    return json.loads(out.stdout)


def locate(place):
    key = place.replace(" ", "")
    for suffix in ("특별자치도", "특별자치시", "특별시", "광역시", "시", "군"):
        if key.endswith(suffix) and key[: -len(suffix)] in CITIES:
            key = key[: -len(suffix)]
    if key in CITIES:
        return key, CITIES[key]
    g = fetch("https://geocoding-api.open-meteo.com/v1/search?count=1&language=ko&name=" + urllib.parse.quote(place))
    if not g.get("results"):
        raise RuntimeError("'%s' 위치를 찾지 못했어요." % place)
    r = g["results"][0]
    return r["name"], (r["latitude"], r["longitude"])


def main():
    place = " ".join(sys.argv[1:]).strip()
    if not place:
        print("사용법: python3 weather.py 지역명")
        return 1
    name, (lat, lon) = locate(place)
    f = fetch(
        "https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s" % (lat, lon)
        + "&current=temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,cloud_cover,wind_speed_10m"
        + "&hourly=temperature_2m,weather_code,precipitation_probability"
        + "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum"
        + "&timezone=Asia%2FSeoul&forecast_days=7"
    )
    c, h, d = f["current"], f["hourly"], f["daily"]
    print("[%s 날씨] %s 기준 (Open-Meteo)" % (name, c["time"].replace("T", " ")))
    print("지금: %s, %.0f도 (체감 %.0f도), 구름 %d%%, 습도 %d%%, 바람 %.1fm/s, 강수 %.1fmm" % (
        sky(c["weather_code"]), c["temperature_2m"], c["apparent_temperature"], c["cloud_cover"],
        c["relative_humidity_2m"], c["wind_speed_10m"] / 3.6, c["precipitation"]))

    start = next((i for i, t in enumerate(h["time"]) if t >= c["time"][:13]), 0)
    hours = []
    for i in range(start, min(start + 24, len(h["time"])), 3):
        hours.append("%s시 %s %.0f도 비%d%%" % (h["time"][i][11:13], sky(h["weather_code"][i]),
                                            h["temperature_2m"][i], h["precipitation_probability"][i] or 0))
    print("앞으로 24시간(3시간 간격): " + " / ".join(hours))

    print("주간:")
    import datetime
    for i, t in enumerate(d["time"]):
        day = datetime.date.fromisoformat(t)
        label = "오늘" if i == 0 else "내일" if i == 1 else DAYS[day.weekday()] + "요일"
        print("  %s(%d일) %s, 최고 %.0f도 최저 %.0f도, 강수확률 %d%%, 강수량 %.1fmm" % (
            label, day.day, sky(d["weather_code"][i]), d["temperature_2m_max"][i], d["temperature_2m_min"][i],
            d["precipitation_probability_max"][i] or 0, d["precipitation_sum"][i] or 0))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        print(e)
        sys.exit(1)
