import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

from .conftest import TODAY, login

# 테스트 전용 가짜 값. 실제 토큰과 관계없다.
TEST_TOKEN = "test-bridge-token"
AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}
URL = "/api/bridge-summary"

# conftest의 TODAY(2026-10-10)는 토요일이다.
SUNDAY = "2026-10-11"
DAILY = {"type": "daily"}
WEEKDAYS = {"type": "weekly", "days": [0, 1, 2, 3, 4]}


@pytest.fixture
def bridge(monkeypatch, logged_in):
    """토큰이 설정된 서버와 로그인한 기기. 자료는 쿠키로 넣고, 요약은 summary()로 읽는다."""
    monkeypatch.setenv("TODO_BRIDGE_TOKEN", TEST_TOKEN)
    return logged_in


def summary() -> dict:
    """Bridge처럼 쿠키 없이 토큰만으로 읽는다."""
    with TestClient(app) as fresh:
        res = fresh.get(URL, headers=AUTH)
    assert res.status_code == 200
    return res.json()


def add_todo(client, text) -> dict:
    res = client.post("/api/todos", json={"text": text, "category": "work"})
    assert res.status_code == 201
    return res.json()


def add_routine(client, text, rule=DAILY) -> dict:
    res = client.post("/api/routines", json={"text": text, "category": "personal", "rule": rule})
    assert res.status_code == 201
    return res.json()


# ---------- 인증 ----------


def test_without_token_is_401(bridge):
    with TestClient(app) as fresh:
        assert fresh.get(URL).status_code == 401


def test_wrong_token_is_401(bridge):
    with TestClient(app) as fresh:
        assert fresh.get(URL, headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert fresh.get(URL, headers={"Authorization": TEST_TOKEN}).status_code == 401
        assert fresh.get(URL, headers={"Authorization": f"Basic {TEST_TOKEN}"}).status_code == 401


def test_cookie_alone_is_401(bridge):
    assert bridge.get(URL).status_code == 401


def test_unset_token_is_always_401(logged_in):
    assert logged_in.get(URL).status_code == 401
    assert logged_in.get(URL, headers={"Authorization": "Bearer "}).status_code == 401
    assert logged_in.get(URL, headers={"Authorization": "Bearer"}).status_code == 401


def test_blank_token_setting_is_always_401(monkeypatch, client):
    monkeypatch.setenv("TODO_BRIDGE_TOKEN", "   ")
    assert client.get(URL, headers={"Authorization": "Bearer    "}).status_code == 401


def test_token_does_not_open_other_apis(bridge):
    with TestClient(app) as fresh:
        assert fresh.get("/api/todos", headers=AUTH).status_code == 401
        assert fresh.get("/api/routines", headers=AUTH).status_code == 401
        assert fresh.post("/api/todos", headers=AUTH, json={"text": "x"}).status_code == 401
        assert fresh.get("/index.html", headers=AUTH, follow_redirects=False).status_code == 303


def test_token_cannot_write(bridge):
    with TestClient(app) as fresh:
        for method in ("post", "put", "patch", "delete"):
            assert getattr(fresh, method)(URL, headers=AUTH).status_code == 401


# ---------- 내용 ----------


def test_empty(bridge):
    assert summary() == {
        "date": TODAY,
        "routines": {"due": 0, "done": 0, "remaining": []},
        "todos": {"remaining_count": 0, "remaining": []},
    }


def test_routines_count_and_remaining_names(bridge):
    add_routine(bridge, "스트레칭")
    done = add_routine(bridge, "영어 단어")
    add_routine(bridge, "독서")
    assert bridge.put(f"/api/routines/{done['id']}/logs/{TODAY}").status_code in (200, 201, 204)
    assert summary()["routines"] == {"due": 3, "done": 1, "remaining": ["스트레칭", "독서"]}


def test_routines_skip_off_days_and_ended(bridge):
    add_routine(bridge, "매일")
    add_routine(bridge, "평일만", WEEKDAYS)  # 오늘은 토요일
    ended = add_routine(bridge, "그만둔 것")
    assert bridge.post(f"/api/routines/{ended['id']}/end").status_code in (200, 204)
    assert summary()["routines"] == {"due": 1, "done": 0, "remaining": ["매일"]}


def test_todos_skip_done_and_group_items(bridge):
    add_todo(bridge, "보고서 초안")
    finished = add_todo(bridge, "끝낸 일")
    assert bridge.patch(f"/api/todos/{finished['id']}", json={"done": True}).status_code == 200
    group = bridge.post("/api/groups", json={"name": "장보기", "category": "personal"}).json()
    assert bridge.post(f"/api/groups/{group['id']}/items", json={"text": "우유, 계란"}).status_code == 201
    assert summary()["todos"] == {"remaining_count": 1, "remaining": ["보고서 초안"]}


def test_todos_follow_app_order(bridge):
    add_todo(bridge, "먼저 적은 것")
    add_todo(bridge, "나중에 적은 것")
    shown = [t["text"] for t in bridge.get("/api/todos").json()["todos"]]
    assert summary()["todos"]["remaining"] == shown


def test_names_are_capped_but_counts_are_not(bridge):
    for n in range(12):
        add_todo(bridge, f"할 일 {n}")
        add_routine(bridge, f"루틴 {n}")
    data = summary()
    assert data["routines"]["due"] == 12
    assert len(data["routines"]["remaining"]) == 10
    assert data["todos"]["remaining_count"] == 12
    assert len(data["todos"]["remaining"]) == 10


def test_date_follows_server_today(bridge, set_today):
    add_routine(bridge, "평일만", WEEKDAYS)
    set_today("2026-10-12")  # 월요일
    data = summary()
    assert data["date"] == "2026-10-12"
    assert data["routines"]["due"] == 1


# ---------- 부작용 없음 ----------


def test_summary_does_not_delete_old_done_todos(bridge, set_today):
    finished = add_todo(bridge, "어제 끝낸 일")
    assert bridge.patch(f"/api/todos/{finished['id']}", json={"done": True}).status_code == 200
    set_today(SUNDAY)
    summary()
    summary()
    store = bridge.app.state.store
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM todos").fetchone()[0] == 1
    # 앱이 목록을 읽을 때는 전과 같이 지운다.
    assert bridge.get("/api/todos").json()["todos"] == []
