"""해빗트래커: 날짜별 상태, 연속 달성일, 달성 수."""

from datetime import date

import pytest

from backend.app import rules

from .conftest import TODAY

# 2026-10-05(월) ~ 2026-10-11(일). conftest의 TODAY(2026-10-10)는 토요일이다.
WEEK = {"start": "2026-10-05", "end": "2026-10-11"}
MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = (
    f"2026-10-{day:02d}" for day in range(5, 12)
)

DAILY = {"type": "daily"}
MON_WED_FRI = {"type": "weekly", "days": [0, 2, 4]}


def d(text: str) -> date:
    return date.fromisoformat(text)


# ---------- 연속 달성일 (계산만) ----------

def streak(logs, today, versions=None, created_on="2026-10-01", ended_on=None) -> int:
    versions = versions or [("2026-10-01", DAILY)]
    return rules.streak(versions, created_on, ended_on, set(logs), d(today))


def test_streak_is_zero_without_logs():
    assert streak([], MONDAY) == 0


def test_streak_counts_consecutive_days_up_to_today():
    assert streak(["2026-10-03", "2026-10-04", MONDAY], MONDAY) == 3


def test_streak_is_kept_when_today_is_not_done_yet():
    assert streak(["2026-10-03", "2026-10-04"], MONDAY) == 2


def test_streak_breaks_at_a_missed_day():
    assert streak(["2026-10-02", "2026-10-04"], MONDAY) == 1  # 3일을 빠뜨렸다
    assert streak(["2026-10-03"], MONDAY) == 0  # 어제를 빠뜨렸다


def test_streak_skips_rest_days():
    versions = [("2026-10-01", MON_WED_FRI)]
    # 금(2일), 월(5일), 수(7일)에 했다. 목요일(8일)은 쉬는 날이라 끊기지 않는다.
    assert streak(["2026-10-02", MONDAY, WEDNESDAY], THURSDAY, versions) == 3
    assert streak(["2026-10-02", WEDNESDAY], THURSDAY, versions) == 1  # 월요일을 빠뜨렸다


def test_streak_does_not_count_days_before_the_routine_existed():
    assert streak(["2026-10-01", "2026-10-02"], "2026-10-02", created_on="2026-10-01") == 2
    assert streak([MONDAY], MONDAY, created_on=MONDAY, versions=[(MONDAY, DAILY)]) == 1


def test_streak_uses_the_rule_of_each_day():
    # 5일(월)부터 수요일만 하는 규칙으로 바꿨다. 그 전은 매일.
    versions = [("2026-10-01", DAILY), (MONDAY, {"type": "weekly", "days": [2]})]
    assert streak(["2026-10-03", "2026-10-04", WEDNESDAY], THURSDAY, versions) == 3


def test_streak_of_an_ended_routine_is_zero():
    assert streak(["2026-10-03", "2026-10-04"], MONDAY, ended_on=MONDAY) == 0


# ---------- 날짜별 상태 (계산만) ----------

def test_statuses_for_a_week():
    statuses = rules.day_statuses(
        [("2026-10-01", MON_WED_FRI)], "2026-10-01", None, {MONDAY}, d(MONDAY), d(SUNDAY), d(FRIDAY)
    )
    assert statuses == ["done", "off", "missed", "off", "pending", "off", "off"]


def test_days_after_today_are_upcoming():
    statuses = rules.day_statuses(
        [("2026-10-01", DAILY)], "2026-10-01", None, set(), d(MONDAY), d(WEDNESDAY), d(MONDAY)
    )
    assert statuses == ["pending", "upcoming", "upcoming"]


def test_days_outside_the_routines_life_are_off():
    # 7일(수)에 만들고 10일(토)에 종료했다.
    statuses = rules.day_statuses(
        [(WEDNESDAY, DAILY)], WEDNESDAY, SATURDAY, {THURSDAY}, d(MONDAY), d(SUNDAY), d("2026-10-12")
    )
    assert statuses == ["off", "off", "missed", "done", "missed", "off", "off"]


# ---------- API ----------

def add(client, text, rule=DAILY, category="personal") -> dict:
    res = client.post("/api/routines", json={"text": text, "category": category, "rule": rule})
    assert res.status_code == 201
    return res.json()


def mark(client, routine, day):
    assert client.put(f"/api/routines/{routine['id']}/logs/{day}").status_code == 204


def habits(client, **params) -> dict:
    res = client.get("/api/habits", params=params or WEEK)
    assert res.status_code == 200
    return res.json()


def test_habits_without_login_is_401(client):
    assert client.get("/api/habits", params=WEEK).status_code == 401


def test_empty_habits(logged_in):
    assert habits(logged_in) == {"today": TODAY, **WEEK, "routines": []}


def test_week_of_a_daily_routine(logged_in, set_today):
    set_today(MONDAY)
    routine = add(logged_in, "운동")
    set_today(SATURDAY)
    for day in (MONDAY, TUESDAY, THURSDAY):
        mark(logged_in, routine, day)

    assert habits(logged_in)["routines"] == [
        {
            "id": routine["id"],
            "text": "운동",
            "category": "personal",
            "rule": DAILY,
            "ended": False,
            "days": ["done", "done", "missed", "done", "missed", "pending", "upcoming"],
            "streak": 0,
            "done": 3,
            "due": 5,
        }
    ]


def test_marking_today_extends_the_streak(logged_in, set_today):
    set_today(THURSDAY)
    routine = add(logged_in, "운동")
    set_today(SATURDAY)
    mark(logged_in, routine, THURSDAY)
    mark(logged_in, routine, FRIDAY)
    assert habits(logged_in)["routines"][0]["streak"] == 2  # 오늘은 아직

    mark(logged_in, routine, SATURDAY)
    after = habits(logged_in)["routines"][0]
    assert after["streak"] == 3
    assert after["days"][5] == "done"


def test_fixing_a_past_day_changes_streak_and_rate(logged_in, set_today):
    set_today(MONDAY)
    routine = add(logged_in, "운동")
    set_today(SATURDAY)
    for day in (MONDAY, TUESDAY, THURSDAY, FRIDAY):
        mark(logged_in, routine, day)
    before = habits(logged_in)["routines"][0]
    assert (before["streak"], before["done"], before["due"]) == (2, 4, 5)

    mark(logged_in, routine, WEDNESDAY)  # 빠뜨린 날을 채운다
    after = habits(logged_in)["routines"][0]
    assert (after["streak"], after["done"], after["due"]) == (5, 5, 5)

    logged_in.delete(f"/api/routines/{routine['id']}/logs/{FRIDAY}")  # 한 날을 지운다
    again = habits(logged_in)["routines"][0]
    assert (again["streak"], again["done"], again["due"]) == (0, 4, 5)


def test_weekly_routine_shows_rest_days(logged_in, set_today):
    set_today(MONDAY)
    routine = add(logged_in, "영어", MON_WED_FRI)
    set_today(SATURDAY)
    mark(logged_in, routine, MONDAY)
    mark(logged_in, routine, FRIDAY)

    shown = habits(logged_in)["routines"][0]
    assert shown["days"] == ["done", "off", "missed", "off", "done", "off", "off"]
    assert shown["streak"] == 1
    assert (shown["done"], shown["due"]) == (2, 3)


def test_ended_routine_stays_in_periods_it_lived_in(logged_in, set_today):
    set_today(MONDAY)
    routine = add(logged_in, "운동")
    mark(logged_in, routine, MONDAY)
    set_today(WEDNESDAY)
    logged_in.post(f"/api/routines/{routine['id']}/end")
    set_today(SATURDAY)

    shown = habits(logged_in)["routines"][0]
    assert shown["ended"] is True
    assert shown["streak"] == 0
    assert shown["days"] == ["done", "missed", "off", "off", "off", "off", "off"]
    # 종료한 뒤의 기간에는 나오지 않는다.
    assert habits(logged_in, start="2026-10-12", end="2026-10-18")["routines"] == []


def test_routine_does_not_appear_before_it_existed(logged_in):
    add(logged_in, "운동")  # 10일(토)에 만들었다
    assert habits(logged_in, start="2026-09-28", end="2026-10-04")["routines"] == []
    assert habits(logged_in)["routines"][0]["days"] == ["off"] * 5 + ["pending", "upcoming"]


def test_month_range(logged_in):
    add(logged_in, "운동")
    month = habits(logged_in, start="2026-10-01", end="2026-10-31")
    assert len(month["routines"][0]["days"]) == 31
    assert month["routines"][0]["days"][9] == "pending"


@pytest.mark.parametrize(
    "params",
    [
        {"start": "2026-10-05"},
        {"end": "2026-10-11"},
        {"start": "2026-10-11", "end": "2026-10-05"},
        {"start": "2026-10-5", "end": "2026-10-11"},
        {"start": "today", "end": "2026-10-11"},
        {"start": "2026-01-01", "end": "2026-12-31"},
    ],
)
def test_bad_ranges_are_rejected(logged_in, params):
    assert logged_in.get("/api/habits", params=params).status_code == 422
