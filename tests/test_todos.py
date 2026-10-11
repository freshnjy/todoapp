import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

from .conftest import TODAY, login


def add(client, text, category="work") -> dict:
    res = client.post("/api/todos", json={"text": text, "category": category})
    assert res.status_code == 201
    return res.json()


def texts(client) -> list[str]:
    return [todo["text"] for todo in client.get("/api/todos").json()["todos"]]


# ---------- 목록과 추가 ----------

def test_empty_list_with_server_today(logged_in):
    res = logged_in.get("/api/todos")
    assert res.status_code == 200
    assert res.json() == {"today": TODAY, "todos": []}


def test_add(logged_in):
    todo = add(logged_in, "보고서 쓰기", "work")
    assert todo == {
        "id": todo["id"],
        "text": "보고서 쓰기",
        "category": "work",
        "done": False,
        "group_id": None,
    }
    assert logged_in.get("/api/todos").json()["todos"] == [todo]


def test_category_defaults_to_work(logged_in):
    res = logged_in.post("/api/todos", json={"text": "카테고리 없이"})
    assert res.status_code == 201
    assert res.json()["category"] == "work"


def test_text_is_trimmed(logged_in):
    assert add(logged_in, "  장보기  ")["text"] == "장보기"


def test_text_of_100_characters_is_allowed(logged_in):
    assert add(logged_in, "가" * 100)["text"] == "가" * 100


@pytest.mark.parametrize(
    "body",
    [
        {"text": ""},
        {"text": "   "},
        {"text": "가" * 101},
        {"text": "운동", "category": "hobby"},
        {"category": "work"},
    ],
)
def test_add_rejects_bad_input(logged_in, body):
    assert logged_in.post("/api/todos", json=body).status_code == 422
    assert texts(logged_in) == []


# ---------- 순서 ----------

def test_new_todo_goes_to_top(logged_in):
    for text in ["A", "B", "C"]:
        add(logged_in, text)
    assert texts(logged_in) == ["C", "B", "A"]


def test_toggling_moves_todo_to_bottom(logged_in):
    add(logged_in, "A")
    b = add(logged_in, "B")
    add(logged_in, "C")

    res = logged_in.patch(f"/api/todos/{b['id']}", json={"done": True})
    assert res.status_code == 200
    assert res.json()["done"] is True
    assert texts(logged_in) == ["C", "A", "B"]

    add(logged_in, "D")
    logged_in.patch(f"/api/todos/{b['id']}", json={"done": False})
    assert texts(logged_in) == ["D", "C", "A", "B"]


def test_editing_text_keeps_position(logged_in):
    a = add(logged_in, "A")
    add(logged_in, "B")
    logged_in.patch(f"/api/todos/{a['id']}", json={"text": "A 고침"})
    assert texts(logged_in) == ["B", "A 고침"]


def test_same_done_value_keeps_position(logged_in):
    a = add(logged_in, "A")
    add(logged_in, "B")
    logged_in.patch(f"/api/todos/{a['id']}", json={"done": False})
    assert texts(logged_in) == ["B", "A"]


# ---------- 수정과 삭제 ----------

def test_edit_text_and_category(logged_in):
    todo = add(logged_in, "공부", "work")
    res = logged_in.patch(
        f"/api/todos/{todo['id']}", json={"text": "  영어 공부 ", "category": "growth"}
    )
    assert res.status_code == 200
    assert res.json() == {
        "id": todo["id"],
        "text": "영어 공부",
        "category": "growth",
        "done": False,
        "group_id": None,
    }


@pytest.mark.parametrize(
    "body", [{"text": ""}, {"text": "  "}, {"text": "가" * 101}, {"category": "hobby"}]
)
def test_edit_rejects_bad_input(logged_in, body):
    todo = add(logged_in, "원래 내용")
    assert logged_in.patch(f"/api/todos/{todo['id']}", json=body).status_code == 422
    assert logged_in.get("/api/todos").json()["todos"] == [todo]


def test_delete(logged_in):
    todo = add(logged_in, "지울 것")
    add(logged_in, "남길 것")
    assert logged_in.delete(f"/api/todos/{todo['id']}").status_code == 204
    assert texts(logged_in) == ["남길 것"]


def test_unknown_id_is_404(logged_in):
    assert logged_in.patch("/api/todos/999", json={"done": True}).status_code == 404
    assert logged_in.delete("/api/todos/999").status_code == 404


def test_clear_done_removes_only_done(logged_in):
    a = add(logged_in, "A")
    b = add(logged_in, "B", "personal")
    add(logged_in, "C")
    for todo in (a, b):
        logged_in.patch(f"/api/todos/{todo['id']}", json={"done": True})

    res = logged_in.post("/api/todos/clear-done")
    assert res.status_code == 200
    assert res.json() == {"deleted": 2}
    assert texts(logged_in) == ["C"]


# ---------- 날짜가 바뀔 때 ----------

def test_done_todos_stay_until_the_day_ends(logged_in):
    todo = add(logged_in, "오늘 끝낸 일")
    logged_in.patch(f"/api/todos/{todo['id']}", json={"done": True})
    assert texts(logged_in) == ["오늘 끝낸 일"]


def test_done_todos_are_removed_on_the_next_day(logged_in, set_today):
    done = add(logged_in, "끝낸 일")
    add(logged_in, "남은 일")
    logged_in.patch(f"/api/todos/{done['id']}", json={"done": True})

    set_today("2026-10-11")
    res = logged_in.get("/api/todos").json()
    assert res["today"] == "2026-10-11"
    assert [todo["text"] for todo in res["todos"]] == ["남은 일"]


def test_unchecked_todo_survives_the_next_day(logged_in, set_today):
    todo = add(logged_in, "체크했다가 푼 일")
    logged_in.patch(f"/api/todos/{todo['id']}", json={"done": True})
    logged_in.patch(f"/api/todos/{todo['id']}", json={"done": False})

    set_today("2026-10-11")
    assert texts(logged_in) == ["체크했다가 푼 일"]


def test_todo_done_today_survives_after_an_old_one_is_removed(logged_in, set_today):
    old = add(logged_in, "어제 끝낸 일")
    logged_in.patch(f"/api/todos/{old['id']}", json={"done": True})

    set_today("2026-10-11")
    new = add(logged_in, "오늘 끝낸 일")
    logged_in.patch(f"/api/todos/{new['id']}", json={"done": True})
    assert texts(logged_in) == ["오늘 끝낸 일"]


# ---------- 저장 ----------

def test_todos_survive_a_restart(logged_in, set_today):
    add(logged_in, "재시작해도 남는 일")

    # 앱을 새로 띄워도(같은 데이터 폴더) 남아 있어야 한다.
    with TestClient(app) as restarted:
        login(restarted)
        assert texts(restarted) == ["재시작해도 남는 일"]
