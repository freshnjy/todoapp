import pytest
from fastapi.testclient import TestClient

from backend.app import auth, todos
from backend.app.main import app

# 테스트 전용 가짜 값. 실제 비밀번호와 관계없다.
TEST_PASSWORD = "test-password"
TEST_SECRET = "test-session-secret"

TODAY = "2026-10-10"


@pytest.fixture(autouse=True)
def todo_env(monkeypatch, tmp_path):
    for name in (
        "TODO_PASSWORD",
        "TODO_SESSION_SECRET",
        "TODO_SESSION_DAYS",
        "TODO_COOKIE_PATH",
        "TODO_COOKIE_SECURE",
        "TODO_DATA_DIR",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TODO_PASSWORD", TEST_PASSWORD)
    monkeypatch.setenv("TODO_SESSION_SECRET", TEST_SECRET)
    # TestClient는 http로 요청하므로 Secure 쿠키를 돌려보내지 않는다.
    monkeypatch.setenv("TODO_COOKIE_PATH", "/")
    monkeypatch.setenv("TODO_COOKIE_SECURE", "false")
    # 테스트마다 빈 저장소로 시작한다.
    monkeypatch.setenv("TODO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(auth, "limiter", auth.LoginLimiter())


@pytest.fixture
def set_today(monkeypatch):
    """서버가 보는 '오늘'을 고정한다. set_today("2026-10-11")로 날짜를 넘긴다."""

    def set_day(day: str) -> None:
        monkeypatch.setattr(todos, "today", lambda: day)

    set_day(TODAY)
    return set_day


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def login(client) -> None:
    res = client.post("/api/session", json={"password": TEST_PASSWORD})
    assert res.status_code == 200


@pytest.fixture
def logged_in(client, set_today):
    login(client)
    return client
