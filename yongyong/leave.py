#!/usr/bin/env python3
"""직원 연차 계산 (회계연도 = 1월 1일 ~ 12월 31일 기준). 데이터: data/leave.json
- 입사 첫해: 한 달 개근할 때마다 1개 (입사일 기준 매달 같은 날에 생김, 1년 동안 최대 11개)
- 입사 다음 해 1월 1일: 15개 × (입사한 해에 일한 날 ÷ 365) + 입사 1년이 될 때까지 남은 달의 월 연차
- 그 다음 해부터: 1월 1일에 15개 (2년마다 1개씩 늘어 최대 25개)
- 연말까지 안 쓴 연차는 하루 통상임금(월급 ÷ 209시간 × 8시간) × 남은 개수만큼 회사가 지급
  python3 leave.py status [이름]                       지금 연차 현황 (이름이 없으면 전체)
  python3 leave.py use 이름 개수 [YYYY-MM-DD] [메모]    연차 사용 기록 (반차는 0.5)
  python3 leave.py cancel 이름                         마지막 사용 기록 취소
  python3 leave.py add 이름 직급 입사일 월급            직원 추가·수정 (예: add 홍길동 대리 2026-12-01 3000000)
  python3 leave.py history 이름                        사용 내역"""
import calendar
import datetime as dt
import json
import sys
import threading
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "leave.json"
_lock = threading.Lock()
DEFAULT = {"employees": {
    "김하진": {"title": "과장", "hire": "2026-10-01", "salary": 3500000, "used": []},
    "임혜빈": {"title": "사원", "hire": "2026-04-01", "salary": 2190000, "used": []},
}}


def load():
    try:
        return json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return json.loads(json.dumps(DEFAULT))


def save(data):
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def monthly_grants(hire):
    """입사 첫해의 월 연차가 생기는 날짜들 (입사 1달, 2달, ... 11달 되는 날)."""
    return [_add_months(hire, n) for n in range(1, 12)]


def granted(emp, year, until=None):
    """year 년에 생긴 연차 개수 (until 날짜까지만, 없으면 그해 12월 31일까지)와 내역."""
    hire = dt.date.fromisoformat(emp["hire"])
    until = until or dt.date(year, 12, 31)
    items = []
    if year < hire.year:
        return 0.0, items
    for g in monthly_grants(hire):  # 첫 1년 동안의 월 연차
        if g.year == year and g <= until:
            items.append((g, 1.0, "월 연차"))
    if year == hire.year + 1 and dt.date(year, 1, 1) <= until:  # 입사 다음 해 1월 1일: 입사한 해에 일한 만큼 비례
        worked = (dt.date(hire.year, 12, 31) - hire).days + 1
        items.append((dt.date(year, 1, 1), round(15 * worked / 365, 1), f"작년 근무 {worked}일 비례"))
    elif year >= hire.year + 2 and dt.date(year, 1, 1) <= until:
        extra = (year - hire.year - 1 - 1) // 2  # 3년차부터 2년마다 1개
        items.append((dt.date(year, 1, 1), float(min(25, 15 + max(0, extra))), "연간 연차"))
    return sum(n for _, n, _ in items), items


def used(emp, year):
    return sum(u["days"] for u in emp.get("used", []) if u["date"].startswith(str(year)))


def daily_wage(emp):
    return round(emp["salary"] * 8 / 209)


def status(name, today=None):
    today = today or dt.date.today()
    data = load()
    emp = data["employees"][name]
    now, items = granted(emp, today.year, today)
    total, all_items = granted(emp, today.year)
    u = used(emp, today.year)
    left_now, left_year = now - u, total - u
    pay = max(0.0, left_year) * daily_wage(emp)
    upcoming = [(d, n) for d, n, _ in all_items if d > today]
    return {"name": name, "title": emp["title"], "hire": emp["hire"], "granted_now": now, "granted_year": total,
            "used": u, "left_now": left_now, "left_year": left_year, "daily_wage": daily_wage(emp), "payout": round(pay),
            "upcoming": upcoming, "salary": emp["salary"]}


def fmt(n):
    return f"{n:g}"


def describe(name, today=None):
    s = status(name, today)
    lines = [f"{s['name']} {s['title']}님 ({s['hire'][:4]}년 {int(s['hire'][5:7])}월 {int(s['hire'][8:])}일 입사)",
             f"지금까지 생긴 연차 {fmt(s['granted_now'])}개, 올해 쓴 연차 {fmt(s['used'])}개, 지금 남은 연차 {fmt(s['left_now'])}개예요."]
    if s["upcoming"]:
        more = sum(n for _, n in s["upcoming"])
        when = ", ".join(f"{d.month}월 {d.day}일" for d, _ in s["upcoming"])
        lines.append(f"올해 안에 {when}에 {fmt(more)}개가 더 생겨서, 올해 연차는 모두 {fmt(s['granted_year'])}개예요.")
    if s["left_year"] > 0:
        lines.append(f"12월 31일까지 {fmt(s['left_year'])}개를 다 안 쓰면, 하루 통상임금 {s['daily_wage']:,}원 × {fmt(s['left_year'])}개 = "
                     f"{s['payout']:,}원을 회사가 연차수당으로 지급해요. (월급 {s['salary']:,}원 ÷ 209시간 × 8시간 기준)")
    else:
        lines.append("올해 연차를 다 써서 연말에 지급할 연차수당은 없어요." if s["left_year"] == 0
                     else f"생길 연차보다 {fmt(-s['left_year'])}개를 더 썼어요 (미리 당겨 쓴 연차).")
    return "\n".join(lines)


def use(name, days, date=None, note=""):
    with _lock:
        data = load()
        emp = data["employees"][name]
        emp.setdefault("used", []).append({"date": (date or dt.date.today()).isoformat(), "days": float(days), "note": note})
        save(data)


def cancel(name):
    with _lock:
        data = load()
        emp = data["employees"][name]
        if not emp.get("used"):
            return None
        last = emp["used"].pop()
        save(data)
        return last


def add(name, title, hire, salary):
    dt.date.fromisoformat(hire)
    with _lock:
        data = load()
        old = data["employees"].get(name, {})
        data["employees"][name] = {"title": title, "hire": hire, "salary": int(salary), "used": old.get("used", [])}
        save(data)


def names():
    return list(load()["employees"])


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else ""
    if cmd == "status":
        for n in (a[1:2] or names()):
            print(describe(n), end="\n\n")
    elif cmd == "use" and len(a) >= 3:
        use(a[1], float(a[2]), dt.date.fromisoformat(a[3]) if len(a) > 3 else None, " ".join(a[4:]))
        print(describe(a[1]))
    elif cmd == "cancel" and len(a) == 2:
        print(cancel(a[1]) or "취소할 기록이 없어요.")
    elif cmd == "add" and len(a) == 5:
        add(a[1], a[2], a[3], int(a[4].replace(",", "")))
        print(describe(a[1]))
    elif cmd == "history" and len(a) == 2:
        for u in load()["employees"][a[1]].get("used", []):
            print(f"{u['date']}  {fmt(u['days'])}개  {u.get('note', '')}")
    else:
        print(__doc__)
