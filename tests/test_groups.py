import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.store import DB_FILENAME

from .conftest import login


def add_group(client, name="장보기", category="personal") -> dict:
    res = client.post("/api/groups", json={"name": name, "category": category})
    assert res.status_code == 201
    return res.json()


def add_items(client, group_id, text) -> list[dict]:
    res = client.post(f"/api/groups/{group_id}/items", json={"text": text})
    assert res.status_code == 201
    return res.json()["todos"]


def todos(client) -> list[dict]:
    return client.get("/api/todos").json()["todos"]


def item_texts(client, group_id) -> list[str]:
    return [todo["text"] for todo in todos(client) if todo["group_id"] == group_id]


def group_names(client) -> list[str]:
    return [group["name"] for group in client.get("/api/groups").json()["groups"]]


# ---------- 묶음 ----------

def test_no_groups_at_first(logged_in):
    res = logged_in.get("/api/groups")
    assert res.status_code == 200
    assert res.json() == {"groups": []}


def test_add_group(logged_in):
    group = add_group(logged_in, "  장보기 ", "personal")
    assert group == {"id": group["id"], "name": "장보기", "category": "personal"}
    assert logged_in.get("/api/groups").json()["groups"] == [group]


def test_group_category_defaults_to_personal(logged_in):
    res = logged_in.post("/api/groups", json={"name": "약국"})
    assert res.status_code == 201
    assert res.json()["category"] == "personal"


def test_groups_are_listed_in_created_order(logged_in):
    for name in ["장보기", "여행 준비물", "약국"]:
        add_group(logged_in, name)
    assert group_names(logged_in) == ["장보기", "여행 준비물", "약국"]


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "가" * 21},
        {"name": "장보기", "category": "hobby"},
        {"category": "personal"},
    ],
)
def test_add_group_rejects_bad_input(logged_in, body):
    assert logged_in.post("/api/groups", json=body).status_code == 422
    assert group_names(logged_in) == []


def test_edit_group_name(logged_in):
    group = add_group(logged_in)
    res = logged_in.patch(f"/api/groups/{group['id']}", json={"name": " 마트 "})
    assert res.status_code == 200
    assert res.json() == {"id": group["id"], "name": "마트", "category": "personal"}


def test_changing_group_category_changes_its_items(logged_in):
    group = add_group(logged_in, "준비물", "personal")
    add_items(logged_in, group["id"], "노트, 펜")
    plain = logged_in.post("/api/todos", json={"text": "보고서", "category": "work"}).json()

    res = logged_in.patch(f"/api/groups/{group['id']}", json={"category": "growth"})
    assert res.json()["category"] == "growth"
    by_id = {todo["id"]: todo for todo in todos(logged_in)}
    assert {t["category"] for t in by_id.values() if t["group_id"] == group["id"]} == {"growth"}
    assert by_id[plain["id"]]["category"] == "work"


@pytest.mark.parametrize("body", [{"name": ""}, {"name": "가" * 21}, {"category": "hobby"}])
def test_edit_group_rejects_bad_input(logged_in, body):
    group = add_group(logged_in)
    assert logged_in.patch(f"/api/groups/{group['id']}", json=body).status_code == 422
    assert logged_in.get("/api/groups").json()["groups"] == [group]


def test_unknown_group_is_404(logged_in):
    assert logged_in.patch("/api/groups/999", json={"name": "없음"}).status_code == 404
    assert logged_in.delete("/api/groups/999").status_code == 404
    assert logged_in.post("/api/groups/999/items", json={"text": "우유"}).status_code == 404
    assert todos(logged_in) == []


def test_groups_need_login(client):
    assert client.get("/api/groups").status_code == 401
    assert client.post("/api/groups", json={"name": "장보기"}).status_code == 401
    assert client.post("/api/groups/1/items", json={"text": "우유"}).status_code == 401


# ---------- 품목 ----------

def test_add_one_item(logged_in):
    group = add_group(logged_in)
    items = add_items(logged_in, group["id"], "  우유 ")
    assert items == [
        {
            "id": items[0]["id"],
            "text": "우유",
            "category": "personal",
            "done": False,
            "group_id": group["id"],
        }
    ]
    assert todos(logged_in) == items


def test_commas_split_into_items_in_typed_order(logged_in):
    group = add_group(logged_in)
    items = add_items(logged_in, group["id"], "우유, 계란 ,두부")
    assert [item["text"] for item in items] == ["우유", "계란", "두부"]
    assert item_texts(logged_in, group["id"]) == ["우유", "계란", "두부"]


def test_empty_pieces_are_dropped(logged_in):
    group = add_group(logged_in)
    add_items(logged_in, group["id"], ",우유,, ,계란,")
    assert item_texts(logged_in, group["id"]) == ["우유", "계란"]


def test_full_width_commas_also_split(logged_in):
    group = add_group(logged_in)
    add_items(logged_in, group["id"], "우유，계란、두부")
    assert item_texts(logged_in, group["id"]) == ["우유", "계란", "두부"]


def test_later_items_go_above_earlier_ones(logged_in):
    group = add_group(logged_in)
    add_items(logged_in, group["id"], "우유, 계란")
    add_items(logged_in, group["id"], "두부")
    assert item_texts(logged_in, group["id"]) == ["두부", "우유", "계란"]


def test_plain_todo_is_not_split_by_commas(logged_in):
    res = logged_in.post("/api/todos", json={"text": "엄마께 전화, 은행 확인", "category": "personal"})
    assert res.status_code == 201
    assert res.json()["group_id"] is None
    assert [todo["text"] for todo in todos(logged_in)] == ["엄마께 전화, 은행 확인"]


@pytest.mark.parametrize(
    "text",
    ["", "   ", " , ,, ", "가" * 101, "우유, " + "가" * 101, "가" * 1001, ",".join(["우유"] * 31)],
)
def test_add_items_rejects_bad_input(logged_in, text):
    group = add_group(logged_in)
    res = logged_in.post(f"/api/groups/{group['id']}/items", json={"text": text})
    assert res.status_code == 422
    assert todos(logged_in) == []


def test_items_missing_text_is_422(logged_in):
    group = add_group(logged_in)
    assert logged_in.post(f"/api/groups/{group['id']}/items", json={}).status_code == 422


def test_item_of_100_characters_is_allowed(logged_in):
    group = add_group(logged_in)
    assert add_items(logged_in, group["id"], "가" * 100)[0]["text"] == "가" * 100


def test_item_can_be_checked_edited_and_deleted_like_a_todo(logged_in):
    group = add_group(logged_in)
    milk, eggs = add_items(logged_in, group["id"], "우유, 계란")

    res = logged_in.patch(f"/api/todos/{milk['id']}", json={"done": True, "text": "저지방 우유"})
    assert res.status_code == 200
    assert res.json() == {**milk, "text": "저지방 우유", "done": True}

    assert logged_in.delete(f"/api/todos/{eggs['id']}").status_code == 204
    assert item_texts(logged_in, group["id"]) == ["저지방 우유"]


def test_item_category_follows_its_group(logged_in):
    group = add_group(logged_in, "장보기", "personal")
    (milk,) = add_items(logged_in, group["id"], "우유")
    res = logged_in.patch(f"/api/todos/{milk['id']}", json={"category": "work"})
    assert res.status_code == 200
    assert res.json()["category"] == "personal"


# ---------- 지우기와 날짜 ----------

def test_deleting_a_group_deletes_its_items_only(logged_in):
    shopping = add_group(logged_in, "장보기")
    trip = add_group(logged_in, "여행 준비물")
    add_items(logged_in, shopping["id"], "우유, 계란")
    add_items(logged_in, trip["id"], "여권")
    logged_in.post("/api/todos", json={"text": "은행 확인"})

    assert logged_in.delete(f"/api/groups/{shopping['id']}").status_code == 204
    assert group_names(logged_in) == ["여행 준비물"]
    assert sorted(todo["text"] for todo in todos(logged_in)) == ["여권", "은행 확인"]


def test_done_items_are_removed_on_the_next_day_but_the_group_stays(logged_in, set_today):
    group = add_group(logged_in)
    milk, eggs = add_items(logged_in, group["id"], "우유, 계란")
    logged_in.patch(f"/api/todos/{milk['id']}", json={"done": True})
    assert item_texts(logged_in, group["id"]) == ["계란", "우유"]

    set_today("2026-10-11")
    assert item_texts(logged_in, group["id"]) == ["계란"]

    logged_in.patch(f"/api/todos/{eggs['id']}", json={"done": True})
    set_today("2026-10-12")
    assert todos(logged_in) == []
    assert logged_in.get("/api/groups").json()["groups"] == [group]


def test_clear_done_also_removes_done_items(logged_in):
    group = add_group(logged_in)
    milk, _eggs = add_items(logged_in, group["id"], "우유, 계란")
    plain = logged_in.post("/api/todos", json={"text": "은행 확인"}).json()
    for todo in (milk, plain):
        logged_in.patch(f"/api/todos/{todo['id']}", json={"done": True})

    assert logged_in.post("/api/todos/clear-done").json() == {"deleted": 2}
    assert [todo["text"] for todo in todos(logged_in)] == ["계란"]
    assert group_names(logged_in) == ["장보기"]


# ---------- 저장 ----------

def test_groups_and_items_survive_a_restart(logged_in, set_today):
    group = add_group(logged_in)
    add_items(logged_in, group["id"], "우유")

    with TestClient(app) as restarted:
        login(restarted)
        assert group_names(restarted) == ["장보기"]
        assert item_texts(restarted, group["id"]) == ["우유"]


def test_old_database_gets_the_new_column(tmp_path, set_today):
    """4단계 전의 파일(group_id 없음)로 시작해도 기존 할 일이 일반 할 일로 남는다."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    conn = sqlite3.connect(data_dir / DB_FILENAME)
    conn.execute(
        "CREATE TABLE todos (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, "
        "category TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, done_on TEXT, "
        "sort_key INTEGER NOT NULL, created_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO todos (text, category, done, sort_key, created_at) "
        "VALUES ('예전 할 일', 'work', 0, 0, '2026-10-09T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    with TestClient(app) as client:
        login(client)
        assert [(t["text"], t["group_id"]) for t in todos(client)] == [("예전 할 일", None)]
        group = add_group(client)
        add_items(client, group["id"], "우유")
        assert item_texts(client, group["id"]) == ["우유"]
