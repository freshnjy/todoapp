import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

from .conftest import TODAY, login

# conftest의 TODAY(2026-10-10)는 토요일이다.
SATURDAY = TODAY
SUNDAY = "2026-10-11"
MONDAY = "2026-10-12"
TUESDAY = "2026-10-13"

DAILY = {"type": "daily"}
MON_WED_FRI = {"type": "weekly", "days": [0, 2, 4]}


def add(client, text, rule=DAILY, category="personal") -> dict:
    res = client.post("/api/routines", json={"text": text, "category": category, "rule": rule})
    assert res.status_code == 201
    return res.json()


def routines(client) -> list[dict]:
    return client.get("/api/routines").json()["routines"]


def by_text(client) -> dict:
    return {routine["text"]: routine for routine in routines(client)}


def mark(client, routine, day):
    return client.put(f"/api/routines/{routine['id']}/logs/{day}")


def unmark(client, routine, day):
    return client.delete(f"/api/routines/{routine['id']}/logs/{day}")


# ---------- 인증 ----------

@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/routines"),
        ("POST", "/api/routines"),
        ("PATCH", "/api/routines/1"),
        ("POST", "/api/routines/1/end"),
        ("PUT", "/api/routines/1/logs/2026-10-10"),
        ("DELETE", "/api/routines/1/logs/2026-10-10"),
    ],
)
def test_routine_api_without_login_is_401(client, method, path):
    res = client.request(method, path, json={"text": "몰래", "rule": DAILY})
    assert res.status_code == 401


# ---------- 목록과 추가 ----------

def test_empty_list_with_server_today(logged_in):
    assert logged_in.get("/api/routines").json() == {"today": TODAY, "routines": []}


def test_add_daily(logged_in):
    routine = add(logged_in, "  스트레칭 ", DAILY, "personal")
    assert routine == {
        "id": routine["id"],
        "text": "스트레칭",
        "category": "personal",
        "rule": {"type": "daily"},
        "due_today": True,
        "done_today": False,
    }
    assert routines(logged_in) == [routine]


def test_routines_are_listed_in_creation_order(logged_in):
    for text in ["A", "B", "C"]:
        add(logged_in, text)
    assert [routine["text"] for routine in routines(logged_in)] == ["A", "B", "C"]


def test_weekly_days_are_sorted_and_deduplicated(logged_in):
    routine = add(logged_in, "영어", {"type": "weekly", "days": [4, 0, 2, 0]})
    assert routine["rule"] == {"type": "weekly", "days": [0, 2, 4]}


def test_extra_rule_fields_are_dropped(logged_in):
    routine = add(logged_in, "운동", {"type": "daily", "days": [1], "day": 5})
    assert routine["rule"] == {"type": "daily"}


@pytest.mark.parametrize(
    "body",
    [
        {"text": "규칙 없음"},
        {"text": "", "rule": DAILY},
        {"text": "가" * 101, "rule": DAILY},
        {"text": "운동", "category": "hobby", "rule": DAILY},
        {"text": "운동", "rule": {"type": "yearly"}},
        {"text": "운동", "rule": {"type": "weekly"}},
        {"text": "운동", "rule": {"type": "weekly", "days": []}},
        {"text": "운동", "rule": {"type": "weekly", "days": [7]}},
        {"text": "운동", "rule": {"type": "weekly", "days": [-1]}},
        {"text": "운동", "rule": {"type": "monthly"}},
        {"text": "운동", "rule": {"type": "monthly", "day": 0}},
        {"text": "운동", "rule": {"type": "monthly", "day": 32}},
    ],
)
def test_add_rejects_bad_input(logged_in, body):
    assert logged_in.post("/api/routines", json=body).status_code == 422
    assert routines(logged_in) == []


def test_routines_do_not_appear_in_todos(logged_in):
    add(logged_in, "운동")
    assert logged_in.get("/api/todos").json()["todos"] == []


# ---------- 오늘 해당하는지 ----------

def test_weekly_routine_is_due_only_on_its_days(logged_in, set_today):
    add(logged_in, "영어", MON_WED_FRI)
    assert by_text(logged_in)["영어"]["due_today"] is False  # 토요일

    set_today(MONDAY)
    assert by_text(logged_in)["영어"]["due_today"] is True

    set_today(TUESDAY)
    assert by_text(logged_in)["영어"]["due_today"] is False


def test_monthly_routine_is_due_on_its_day(logged_in, set_today):
    add(logged_in, "정산", {"type": "monthly", "day": 25})
    assert by_text(logged_in)["정산"]["due_today"] is False

    set_today("2026-10-25")
    assert by_text(logged_in)["정산"]["due_today"] is True


def test_monthly_31_is_due_on_the_last_day_of_a_short_month(logged_in, set_today):
    add(logged_in, "말일 정리", {"type": "monthly", "day": 31})
    set_today("2026-11-29")
    assert by_text(logged_in)["말일 정리"]["due_today"] is False
    set_today("2026-11-30")
    assert by_text(logged_in)["말일 정리"]["due_today"] is True


# ---------- 수행 기록 ----------

def test_mark_and_unmark_today(logged_in):
    routine = add(logged_in, "운동")
    assert mark(logged_in, routine, SATURDAY).status_code == 204
    assert by_text(logged_in)["운동"]["done_today"] is True

    assert unmark(logged_in, routine, SATURDAY).status_code == 204
    assert by_text(logged_in)["운동"]["done_today"] is False


def test_marking_twice_is_fine(logged_in):
    routine = add(logged_in, "운동")
    assert mark(logged_in, routine, SATURDAY).status_code == 204
    assert mark(logged_in, routine, SATURDAY).status_code == 204
    assert unmark(logged_in, routine, SATURDAY).status_code == 204
    assert unmark(logged_in, routine, SATURDAY).status_code == 204
    assert by_text(logged_in)["운동"]["done_today"] is False


def test_routine_is_unchecked_again_the_next_day(logged_in, set_today):
    routine = add(logged_in, "운동")
    mark(logged_in, routine, SATURDAY)

    set_today(SUNDAY)
    today = by_text(logged_in)["운동"]
    assert today["due_today"] is True
    assert today["done_today"] is False


def test_yesterday_can_still_be_marked(logged_in, set_today):
    routine = add(logged_in, "운동")
    set_today(SUNDAY)
    assert mark(logged_in, routine, SATURDAY).status_code == 204
    assert by_text(logged_in)["운동"]["done_today"] is False  # 오늘 기록은 아니다


def test_cannot_mark_a_future_day(logged_in):
    routine = add(logged_in, "운동")
    assert mark(logged_in, routine, SUNDAY).status_code == 422


def test_cannot_mark_a_day_that_is_not_due(logged_in, set_today):
    routine = add(logged_in, "영어", MON_WED_FRI)
    assert mark(logged_in, routine, SATURDAY).status_code == 422
    set_today(TUESDAY)
    assert mark(logged_in, routine, MONDAY).status_code == 204
    assert mark(logged_in, routine, TUESDAY).status_code == 422


def test_cannot_mark_a_day_before_the_routine_existed(logged_in):
    routine = add(logged_in, "운동")
    assert mark(logged_in, routine, "2026-10-09").status_code == 422


@pytest.mark.parametrize("day", ["today", "2026-13-01", "2026-10-1", "20261010"])
def test_bad_dates_are_rejected(logged_in, day):
    routine = add(logged_in, "운동")
    assert mark(logged_in, routine, day).status_code == 422


def test_unknown_routine_is_404(logged_in):
    assert logged_in.put(f"/api/routines/999/logs/{SATURDAY}").status_code == 404
    assert logged_in.patch("/api/routines/999", json={"text": "없음"}).status_code == 404
    assert logged_in.post("/api/routines/999/end").status_code == 404


# ---------- 수정 ----------

def test_edit_text_and_category(logged_in):
    routine = add(logged_in, "운동", DAILY, "personal")
    res = logged_in.patch(
        f"/api/routines/{routine['id']}", json={"text": " 달리기 ", "category": "growth"}
    )
    assert res.status_code == 200
    assert res.json() == {**routine, "text": "달리기", "category": "growth"}


@pytest.mark.parametrize(
    "body",
    [{"text": " "}, {"category": "hobby"}, {"rule": {"type": "weekly", "days": []}}],
)
def test_edit_rejects_bad_input(logged_in, body):
    routine = add(logged_in, "운동")
    assert logged_in.patch(f"/api/routines/{routine['id']}", json=body).status_code == 422
    assert routines(logged_in) == [routine]


def test_rule_change_applies_from_today_and_keeps_the_past(logged_in, set_today):
    routine = add(logged_in, "운동", DAILY)  # 토요일에 만든 매일 루틴
    mark(logged_in, routine, SATURDAY)

    set_today(MONDAY)
    res = logged_in.patch(f"/api/routines/{routine['id']}", json={"rule": {"type": "weekly", "days": [1]}})
    assert res.json()["rule"] == {"type": "weekly", "days": [1]}  # 화요일만
    assert res.json()["due_today"] is False

    set_today(TUESDAY)
    # 바꾸기 전(일요일)은 당시 규칙(매일)이라 기록할 수 있다.
    assert mark(logged_in, routine, SUNDAY).status_code == 204
    # 바꾼 날(월요일)부터는 새 규칙이라 월요일은 하는 날이 아니다.
    assert mark(logged_in, routine, MONDAY).status_code == 422
    assert mark(logged_in, routine, TUESDAY).status_code == 204
    # 지난 기록은 그대로 남아 있어 지울 수 있다.
    assert unmark(logged_in, routine, SATURDAY).status_code == 204


def test_rule_changed_twice_on_the_same_day_keeps_the_last(logged_in):
    routine = add(logged_in, "운동", DAILY)
    logged_in.patch(f"/api/routines/{routine['id']}", json={"rule": MON_WED_FRI})
    res = logged_in.patch(f"/api/routines/{routine['id']}", json={"rule": {"type": "weekly", "days": [5]}})
    assert res.json()["rule"] == {"type": "weekly", "days": [5]}
    assert res.json()["due_today"] is True  # 토요일


# ---------- 종료 ----------

def test_end_removes_from_list_but_keeps_the_past(logged_in, set_today):
    routine = add(logged_in, "운동")
    add(logged_in, "독서")
    mark(logged_in, routine, SATURDAY)

    set_today(MONDAY)
    assert logged_in.post(f"/api/routines/{routine['id']}/end").status_code == 204
    assert [item["text"] for item in routines(logged_in)] == ["독서"]

    # 종료한 뒤에는 고칠 수 없고, 다시 종료할 수도 없다.
    assert logged_in.patch(f"/api/routines/{routine['id']}", json={"text": "x"}).status_code == 404
    assert logged_in.post(f"/api/routines/{routine['id']}/end").status_code == 404
    # 종료하기 전 날짜의 기록은 남아 있고 고칠 수 있다. 종료한 날부터는 하는 날이 아니다.
    assert mark(logged_in, routine, SUNDAY).status_code == 204
    assert unmark(logged_in, routine, SATURDAY).status_code == 204
    assert mark(logged_in, routine, MONDAY).status_code == 422


# ---------- 저장 ----------

def test_routines_and_logs_survive_a_restart(logged_in, set_today):
    routine = add(logged_in, "운동")
    mark(logged_in, routine, SATURDAY)

    with TestClient(app) as restarted:
        login(restarted)
        assert by_text(restarted)["운동"]["done_today"] is True


def test_clearing_done_todos_does_not_touch_routines(logged_in):
    routine = add(logged_in, "운동")
    mark(logged_in, routine, SATURDAY)
    assert logged_in.post("/api/todos/clear-done").json() == {"deleted": 0}
    assert by_text(logged_in)["운동"]["done_today"] is True
