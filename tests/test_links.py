"""할 일에 메모 연결 (10단계)."""

import pytest

from backend.app import clock


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: "2026-10-10T09:00:00+09:00")


def add_todo(client, text="코스트코 가기") -> dict:
    res = client.post("/api/todos", json={"text": text, "category": "personal"})
    assert res.status_code == 201
    return res.json()


def add_memo(client, title, items=None) -> dict:
    res = client.post("/api/memos", json={"title": title, "items": items})
    assert res.status_code == 201, res.text
    return res.json()


def link(client, todo_id, memo_ids):
    return client.put(f"/api/todos/{todo_id}/memos", json={"memo_ids": memo_ids})


def get_todo(client, todo_id) -> dict:
    return next(t for t in client.get("/api/todos").json()["todos"] if t["id"] == todo_id)


def get_memo(client, memo_id) -> dict:
    return next(m for m in client.get("/api/memos").json()["memos"] if m["id"] == memo_id)


def check(client, memo, text, done=True):
    item = next(i for i in memo["items"] if i["text"] == text)
    res = client.patch(f"/api/memos/{memo['id']}/items/{item['id']}", json={"done": done})
    assert res.status_code == 200
    return res.json()


def item_state(memo) -> list[tuple[str, bool]]:
    return [(item["text"], item["done"]) for item in memo["items"]]


# ---------- 연결하기 ----------

def test_new_todo_has_no_memos(logged_in):
    assert add_todo(logged_in)["memo_ids"] == []


def test_link_and_unlink(logged_in):
    todo = add_todo(logged_in)
    shop = add_memo(logged_in, "장보기", "우유")
    pack = add_memo(logged_in, "짐싸기")

    res = link(logged_in, todo["id"], [shop["id"], pack["id"], shop["id"]])
    assert res.status_code == 200
    assert res.json()["memo_ids"] == [shop["id"], pack["id"]]  # 겹친 것은 한 번만
    assert get_todo(logged_in, todo["id"])["memo_ids"] == [shop["id"], pack["id"]]

    # 이미 붙어 있던 것은 자리를 지키고, 뗀 것만 빠진다
    assert link(logged_in, todo["id"], [pack["id"]]).json()["memo_ids"] == [pack["id"]]
    assert link(logged_in, todo["id"], []).json()["memo_ids"] == []
    # 떼어도 메모는 그대로
    assert item_state(get_memo(logged_in, shop["id"])) == [("우유", False)]


def test_one_memo_on_several_todos(logged_in):
    shop = add_memo(logged_in, "장보기")
    first, second = add_todo(logged_in, "코스트코 가기"), add_todo(logged_in, "마트 가기")
    link(logged_in, first["id"], [shop["id"]])
    link(logged_in, second["id"], [shop["id"]])
    assert get_todo(logged_in, first["id"])["memo_ids"] == [shop["id"]]
    assert get_todo(logged_in, second["id"])["memo_ids"] == [shop["id"]]


def test_link_errors(logged_in):
    todo = add_todo(logged_in)
    shop = add_memo(logged_in, "장보기")
    assert link(logged_in, 999, [shop["id"]]).status_code == 404
    assert link(logged_in, todo["id"], [shop["id"], 999]).status_code == 404
    # 없는 메모가 섞이면 아무것도 바꾸지 않는다
    assert get_todo(logged_in, todo["id"])["memo_ids"] == []
    assert logged_in.put(f"/api/todos/{todo['id']}/memos", json={"memo_ids": "1"}).status_code == 422


def test_link_needs_login(client):
    assert client.put("/api/todos/1/memos", json={"memo_ids": []}).status_code == 401


def test_routines_have_no_memo_link(logged_in):
    res = logged_in.post("/api/routines", json={"text": "스트레칭", "category": "growth", "rule": {"type": "daily"}})
    assert res.status_code == 201
    routine_id = res.json()["id"]
    assert logged_in.put(f"/api/routines/{routine_id}/memos", json={"memo_ids": []}).status_code in (404, 405)
    assert "memo_ids" not in res.json()


# ---------- 완료해도 메모는 그대로 (체크 표시만 남는다) ----------

def test_completing_keeps_linked_memos_as_they_are(logged_in):
    todo = add_todo(logged_in)
    shop = add_memo(logged_in, "장보기", "우유, 계란, 두부")
    pack = add_memo(logged_in, "짐싸기", "여권, 충전기")
    check(logged_in, shop, "우유")
    check(logged_in, shop, "두부")
    check(logged_in, pack, "여권")
    link(logged_in, todo["id"], [shop["id"], pack["id"]])
    before = logged_in.get("/api/memos").json()["memos"]

    res = logged_in.patch(f"/api/todos/{todo['id']}", json={"done": True})
    assert res.status_code == 200 and res.json()["done"] is True
    assert item_state(get_memo(logged_in, shop["id"])) == [("우유", True), ("계란", False), ("두부", True)]
    assert item_state(get_memo(logged_in, pack["id"])) == [("여권", True), ("충전기", False)]
    # 메모의 순서와 고친 시각도 바뀌지 않는다
    assert logged_in.get("/api/memos").json()["memos"] == before
    # 연결은 그대로 남는다
    assert get_todo(logged_in, todo["id"])["memo_ids"] == [shop["id"], pack["id"]]


def test_unchecking_the_todo_keeps_memos_too(logged_in):
    todo = add_todo(logged_in)
    shop = add_memo(logged_in, "장보기", "우유, 계란")
    check(logged_in, shop, "우유")
    link(logged_in, todo["id"], [shop["id"]])
    logged_in.patch(f"/api/todos/{todo['id']}", json={"done": True})
    logged_in.patch(f"/api/todos/{todo['id']}", json={"done": False})
    assert item_state(get_memo(logged_in, shop["id"])) == [("우유", True), ("계란", False)]


# ---------- 지우면 연결도 없어진다 ----------

def test_deleting_the_todo_removes_links_but_keeps_the_memo(logged_in):
    todo = add_todo(logged_in)
    shop = add_memo(logged_in, "장보기", "우유")
    link(logged_in, todo["id"], [shop["id"]])
    assert logged_in.delete(f"/api/todos/{todo['id']}").status_code == 204
    assert item_state(get_memo(logged_in, shop["id"])) == [("우유", False)]
    # 같은 메모를 다른 할 일에 붙여도 지난 연결이 섞이지 않는다
    again = add_todo(logged_in, "다시")
    assert link(logged_in, again["id"], [shop["id"]]).json()["memo_ids"] == [shop["id"]]


def test_deleting_the_memo_removes_it_from_todos(logged_in):
    todo = add_todo(logged_in)
    shop = add_memo(logged_in, "장보기")
    pack = add_memo(logged_in, "짐싸기")
    link(logged_in, todo["id"], [shop["id"], pack["id"]])
    assert logged_in.delete(f"/api/memos/{shop['id']}").status_code == 204
    assert get_todo(logged_in, todo["id"])["memo_ids"] == [pack["id"]]


def test_cleared_done_todos_drop_their_links(logged_in, set_today):
    done = add_todo(logged_in, "어제 끝낸 일")
    left = add_todo(logged_in, "남은 일")
    shop = add_memo(logged_in, "장보기", "우유")
    link(logged_in, done["id"], [shop["id"]])
    link(logged_in, left["id"], [shop["id"]])
    logged_in.patch(f"/api/todos/{done['id']}", json={"done": True})

    set_today("2026-10-11")
    todos = logged_in.get("/api/todos").json()["todos"]
    assert [(t["text"], t["memo_ids"]) for t in todos] == [("남은 일", [shop["id"]])]
    assert item_state(get_memo(logged_in, shop["id"])) == [("우유", False)]


def test_clear_done_button_drops_links(logged_in):
    todo = add_todo(logged_in)
    shop = add_memo(logged_in, "장보기")
    link(logged_in, todo["id"], [shop["id"]])
    logged_in.patch(f"/api/todos/{todo['id']}", json={"done": True})
    assert logged_in.post("/api/todos/clear-done").json() == {"deleted": 1}
    new = add_todo(logged_in, "새 할 일")
    assert link(logged_in, new["id"], []).json()["memo_ids"] == []
    assert get_memo(logged_in, shop["id"])["title"] == "장보기"


def test_bridge_summary_is_unchanged_by_links(logged_in, monkeypatch):
    monkeypatch.setenv("TODO_BRIDGE_TOKEN", "test-bridge-token")
    todo = add_todo(logged_in)
    shop = add_memo(logged_in, "장보기", "우유")
    link(logged_in, todo["id"], [shop["id"]])
    res = logged_in.get("/api/bridge-summary", headers={"Authorization": "Bearer test-bridge-token"})
    assert res.json()["todos"] == {"remaining_count": 1, "remaining": ["코스트코 가기"]}
