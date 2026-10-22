"""저장소(메모) API. 8단계."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.app import clock
from backend.app.main import app
from backend.app.store import DB_FILENAME

from .conftest import login


@pytest.fixture
def set_now(monkeypatch):
    """서버가 보는 '지금'을 고정한다. set_now("2026-10-12T09:00:00+09:00")."""

    def set_time(value: str) -> None:
        monkeypatch.setattr(clock, "now", lambda: value)

    set_time("2026-10-10T09:00:00+09:00")
    return set_time


def add_memo(client, **fields) -> dict:
    res = client.post("/api/memos", json=fields)
    assert res.status_code == 201, res.text
    return res.json()


def memos(client) -> list[dict]:
    res = client.get("/api/memos")
    assert res.status_code == 200
    return res.json()["memos"]


def titles(client) -> list:
    return [memo["title"] for memo in memos(client)]


def item_texts(memo) -> list[str]:
    return [item["text"] for item in memo["items"]]


# ---------- 메모 만들기 ----------

def test_no_memos_at_first(logged_in):
    assert memos(logged_in) == []


def test_add_memo_with_title_body_and_items(logged_in, set_now):
    memo = add_memo(logged_in, title=" 장보기 ", body="코스트코에서\n", items="우유, 소고기 ,, 두부")
    assert memo["title"] == "장보기"
    assert memo["body"] == "코스트코에서"
    assert item_texts(memo) == ["우유", "소고기", "두부"]
    assert all(item["done"] is False for item in memo["items"])
    assert memo["created_at"] == memo["updated_at"] == "2026-10-10T09:00:00+09:00"
    assert memo["items"][0]["created_at"] == "2026-10-10T09:00:00+09:00"
    assert memos(logged_in) == [memo]


def test_memo_with_only_body(logged_in):
    memo = add_memo(logged_in, body="떠오른 생각 하나")
    assert memo["title"] is None
    assert memo["items"] == []


def test_memo_with_only_title(logged_in):
    memo = add_memo(logged_in, title="여행 준비물")
    assert memo["body"] == "" and memo["items"] == []


@pytest.mark.parametrize("fields", [{}, {"title": "  ", "body": " \n ", "items": " , "}])
def test_empty_memo_is_rejected(logged_in, fields):
    res = logged_in.post("/api/memos", json=fields)
    assert res.status_code == 422
    assert memos(logged_in) == []


def test_untitled_memos_can_be_many(logged_in):
    add_memo(logged_in, body="하나")
    add_memo(logged_in, body="둘")
    assert titles(logged_in) == [None, None]


@pytest.mark.parametrize("other", ["장보기", "장 보기", " 장보기 "])
def test_same_title_is_rejected(logged_in, other):
    add_memo(logged_in, title="장보기")
    res = logged_in.post("/api/memos", json={"title": other, "body": "x"})
    assert res.status_code == 409
    assert titles(logged_in) == ["장보기"]


def test_same_title_ignores_letter_case(logged_in):
    add_memo(logged_in, title="Costco")
    assert logged_in.post("/api/memos", json={"title": "costco"}).status_code == 409


@pytest.mark.parametrize(
    "fields",
    [
        {"title": "가" * 21},
        {"body": "가" * 2001},
        {"items": "가" * 101},
        {"items": ",".join(["우유"] * 31)},
    ],
)
def test_too_long_is_rejected(logged_in, fields):
    assert logged_in.post("/api/memos", json=fields).status_code == 422


def test_longest_allowed(logged_in):
    memo = add_memo(logged_in, title="가" * 20, body="나" * 2000, items=",".join(["다" * 100] * 3))
    assert len(memo["items"]) == 3


# ---------- 목록 순서 ----------

def test_recently_changed_memo_comes_first(logged_in, set_now):
    first = add_memo(logged_in, title="장보기")
    add_memo(logged_in, title="짐싸기")
    add_memo(logged_in, title="아이디어")
    assert titles(logged_in) == ["아이디어", "짐싸기", "장보기"]

    set_now("2026-10-11T08:00:00+09:00")
    logged_in.post(f"/api/memos/{first['id']}/items", json={"text": "우유"})
    assert titles(logged_in) == ["장보기", "아이디어", "짐싸기"]
    assert memos(logged_in)[0]["updated_at"] == "2026-10-11T08:00:00+09:00"
    assert memos(logged_in)[0]["created_at"] == "2026-10-10T09:00:00+09:00"


def test_checking_an_item_moves_memo_up(logged_in):
    memo = add_memo(logged_in, title="장보기", items="우유")
    add_memo(logged_in, title="짐싸기")
    item = memo["items"][0]
    logged_in.patch(f"/api/memos/{memo['id']}/items/{item['id']}", json={"done": True})
    assert titles(logged_in) == ["장보기", "짐싸기"]


# ---------- 메모 고치기 ----------

def test_update_title_and_body(logged_in, set_now):
    memo = add_memo(logged_in, title="장보기", items="우유")
    set_now("2026-10-12T20:00:00+09:00")
    res = logged_in.patch(f"/api/memos/{memo['id']}", json={"title": "코스트코", "body": "주말에"})
    assert res.status_code == 200
    updated = res.json()
    assert (updated["title"], updated["body"]) == ("코스트코", "주말에")
    assert item_texts(updated) == ["우유"]
    assert updated["updated_at"] == "2026-10-12T20:00:00+09:00"
    assert updated["created_at"] == "2026-10-10T09:00:00+09:00"


def test_update_only_given_fields(logged_in):
    memo = add_memo(logged_in, title="장보기", body="주말에")
    updated = logged_in.patch(f"/api/memos/{memo['id']}", json={"body": "토요일"}).json()
    assert updated["title"] == "장보기"
    updated = logged_in.patch(f"/api/memos/{memo['id']}", json={"title": "장 보기"}).json()
    assert updated["body"] == "토요일"


@pytest.mark.parametrize("cleared", [None, "", "   "])
def test_clear_title(logged_in, cleared):
    memo = add_memo(logged_in, title="장보기", body="우유 사기")
    updated = logged_in.patch(f"/api/memos/{memo['id']}", json={"title": cleared}).json()
    assert updated["title"] is None


def test_keeping_own_title_is_not_a_duplicate(logged_in):
    memo = add_memo(logged_in, title="장보기")
    res = logged_in.patch(f"/api/memos/{memo['id']}", json={"title": "장 보기"})
    assert res.status_code == 200


def test_rename_to_other_memos_title_is_rejected(logged_in):
    add_memo(logged_in, title="장보기")
    other = add_memo(logged_in, title="짐싸기")
    res = logged_in.patch(f"/api/memos/{other['id']}", json={"title": "장보기"})
    assert res.status_code == 409
    assert logged_in.get("/api/memos").json()["memos"][0]["title"] == "짐싸기"


def test_update_that_empties_memo_is_rejected(logged_in):
    memo = add_memo(logged_in, title="장보기")
    res = logged_in.patch(f"/api/memos/{memo['id']}", json={"title": ""})
    assert res.status_code == 422
    assert titles(logged_in) == ["장보기"]


def test_update_unknown_memo(logged_in):
    assert logged_in.patch("/api/memos/999", json={"body": "x"}).status_code == 404


# ---------- 메모 지우기 ----------

def test_delete_memo_with_items(logged_in, client):
    memo = add_memo(logged_in, title="장보기", items="우유, 계란")
    other = add_memo(logged_in, title="짐싸기", items="여권")
    assert logged_in.delete(f"/api/memos/{memo['id']}").status_code == 204
    assert titles(logged_in) == ["짐싸기"]
    assert logged_in.delete(f"/api/memos/{memo['id']}").status_code == 404
    path = logged_in.app.state.store.path
    with sqlite3.connect(path) as conn:
        left = [row[0] for row in conn.execute("SELECT text FROM memo_items")]
    assert left == ["여권"]
    assert item_texts(memos(logged_in)[0]) == item_texts(other)


# ---------- 품목 ----------

def test_add_items_split_by_commas_go_to_bottom(logged_in, set_now):
    memo = add_memo(logged_in, title="장보기", items="우유")
    set_now("2026-10-11T07:30:00+09:00")
    res = logged_in.post(f"/api/memos/{memo['id']}/items", json={"text": "소고기， 두부、계란"})
    assert res.status_code == 201
    updated = res.json()
    assert item_texts(updated) == ["우유", "소고기", "두부", "계란"]
    assert updated["items"][0]["created_at"] == "2026-10-10T09:00:00+09:00"
    assert updated["items"][-1]["created_at"] == "2026-10-11T07:30:00+09:00"


def test_add_items_to_memo_without_items(logged_in):
    memo = add_memo(logged_in, body="그냥 메모")
    updated = logged_in.post(f"/api/memos/{memo['id']}/items", json={"text": "하나"}).json()
    assert item_texts(updated) == ["하나"]


@pytest.mark.parametrize("text", ["", " , ", "가" * 101])
def test_bad_items_are_rejected(logged_in, text):
    memo = add_memo(logged_in, title="장보기")
    assert logged_in.post(f"/api/memos/{memo['id']}/items", json={"text": text}).status_code == 422


def test_add_items_to_unknown_memo(logged_in):
    assert logged_in.post("/api/memos/999/items", json={"text": "우유"}).status_code == 404


def test_check_keeps_item_in_place(logged_in):
    memo = add_memo(logged_in, title="장보기", items="우유, 소고기, 두부")
    first = memo["items"][0]
    updated = logged_in.patch(f"/api/memos/{memo['id']}/items/{first['id']}", json={"done": True}).json()
    assert item_texts(updated) == ["우유", "소고기", "두부"]
    assert [item["done"] for item in updated["items"]] == [True, False, False]
    updated = logged_in.patch(f"/api/memos/{memo['id']}/items/{first['id']}", json={"done": False}).json()
    assert [item["done"] for item in updated["items"]] == [False, False, False]


def test_checked_item_stays_on_the_next_day(logged_in, set_today):
    memo = add_memo(logged_in, title="장보기", items="우유")
    item = memo["items"][0]
    logged_in.patch(f"/api/memos/{memo['id']}/items/{item['id']}", json={"done": True})
    set_today("2026-10-20")
    logged_in.get("/api/todos")  # 할 일 목록의 날짜 정리가 메모를 건드리지 않는다
    logged_in.post("/api/todos/clear-done")  # 할 일의 "완료 항목 지우기"도 마찬가지
    assert memos(logged_in)[0]["items"][0]["done"] is True


def test_edit_item_text(logged_in):
    memo = add_memo(logged_in, title="장보기", items="우유")
    item = memo["items"][0]
    url = f"/api/memos/{memo['id']}/items/{item['id']}"
    assert item_texts(logged_in.patch(url, json={"text": " 저지방 우유 "}).json()) == ["저지방 우유"]
    assert logged_in.patch(url, json={"text": "  "}).status_code == 422
    assert logged_in.patch(url, json={"text": "가" * 101}).status_code == 422


def test_item_of_other_memo_is_not_found(logged_in):
    memo = add_memo(logged_in, title="장보기", items="우유")
    other = add_memo(logged_in, title="짐싸기")
    item = memo["items"][0]
    assert logged_in.patch(f"/api/memos/{other['id']}/items/{item['id']}", json={"done": True}).status_code == 404
    assert logged_in.delete(f"/api/memos/{other['id']}/items/{item['id']}").status_code == 404


def test_delete_item(logged_in):
    memo = add_memo(logged_in, title="장보기", items="우유, 계란")
    item = memo["items"][0]
    res = logged_in.delete(f"/api/memos/{memo['id']}/items/{item['id']}")
    assert res.status_code == 200
    assert item_texts(res.json()) == ["계란"]


def test_clear_checked_items(logged_in):
    memo = add_memo(logged_in, title="장보기", items="우유, 계란, 두부")
    for item in memo["items"][:2]:
        logged_in.patch(f"/api/memos/{memo['id']}/items/{item['id']}", json={"done": True})
    res = logged_in.post(f"/api/memos/{memo['id']}/clear-done")
    assert res.status_code == 200
    assert item_texts(res.json()) == ["두부"]
    assert logged_in.post("/api/memos/999/clear-done").status_code == 404


# ---------- 다른 기능과 섞이지 않는지 ----------

def test_memos_do_not_touch_todos_or_bridge(logged_in, monkeypatch):
    logged_in.post("/api/todos", json={"text": "코스트코 가기", "category": "personal"})
    add_memo(logged_in, title="장보기", items="우유, 소고기")
    assert [todo["text"] for todo in logged_in.get("/api/todos").json()["todos"]] == ["코스트코 가기"]
    monkeypatch.setenv("TODO_BRIDGE_TOKEN", "test-bridge-token")
    summary = logged_in.get(
        "/api/bridge-summary", headers={"Authorization": "Bearer test-bridge-token"}
    ).json()
    assert summary["todos"] == {"remaining_count": 1, "remaining": ["코스트코 가기"]}


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/api/memos"),
        ("POST", "/api/memos"),
        ("PATCH", "/api/memos/1"),
        ("DELETE", "/api/memos/1"),
        ("POST", "/api/memos/1/items"),
        ("PATCH", "/api/memos/1/items/1"),
        ("DELETE", "/api/memos/1/items/1"),
        ("POST", "/api/memos/1/clear-done"),
    ],
)
def test_memos_need_login(client, method, path):
    assert client.request(method, path, json={}).status_code == 401


def test_memos_survive_restart(tmp_path):
    with TestClient(app) as first:
        login(first)
        add_memo(first, title="장보기", items="우유")
    with TestClient(app) as second:
        login(second)
        assert item_texts(memos(second)[0]) == ["우유"]


def test_old_database_gets_memo_tables(tmp_path):
    """8단계 전의 데이터베이스 파일(메모 테이블 없음)을 열어도 할 일은 그대로이고 메모를 쓸 수 있다."""
    path = tmp_path / "data" / DB_FILENAME
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE todos (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, "
            "category TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, done_on TEXT, "
            "sort_key INTEGER NOT NULL, created_at TEXT NOT NULL, group_id INTEGER)"
        )
        conn.execute(
            "INSERT INTO todos (text, category, sort_key, created_at) VALUES ('은행 가기', 'personal', 0, 'x')"
        )
    with TestClient(app) as c:
        login(c)
        assert [todo["text"] for todo in c.get("/api/todos").json()["todos"]] == ["은행 가기"]
        add_memo(c, title="장보기")
        assert titles(c) == ["장보기"]


def test_old_groups_and_their_items_are_removed_on_start(tmp_path):
    """9단계: 묶음 데이터는 옮기지 않고 지운다. 일반 할 일과 메모는 그대로 둔다."""
    path = tmp_path / "data" / DB_FILENAME
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE todos (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, "
            "category TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, done_on TEXT, "
            "sort_key INTEGER NOT NULL, created_at TEXT NOT NULL, group_id INTEGER)"
        )
        conn.execute(
            "CREATE TABLE groups (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
            "category TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO groups (name, category, created_at) VALUES ('코스트코', 'personal', 'x')")
        conn.execute(
            "INSERT INTO todos (text, category, sort_key, created_at) VALUES ('은행 가기', 'personal', 0, 'x')"
        )
        conn.execute(
            "INSERT INTO todos (text, category, sort_key, created_at, group_id) VALUES ('우유', 'personal', 1, 'x', 1)"
        )
    with TestClient(app) as c:
        login(c)
        assert c.get("/api/todos").json()["todos"] == [
            {"id": 1, "text": "은행 가기", "category": "personal", "done": False, "memo_ids": []}
        ]
        assert c.get("/api/groups").status_code in (404, 405)
        add_memo(c, title="장보기", items="두부")
    with sqlite3.connect(path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "groups" not in tables
    # 다시 시작해도 문제없고 남은 것은 그대로다
    with TestClient(app) as c:
        login(c)
        assert [todo["text"] for todo in c.get("/api/todos").json()["todos"]] == ["은행 가기"]
        assert titles(c) == ["장보기"]
