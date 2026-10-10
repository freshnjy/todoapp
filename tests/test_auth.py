import time

import pytest

from backend.app import auth

from .conftest import TEST_PASSWORD, TEST_SECRET


def set_cookie_header(res) -> str:
    return res.headers["set-cookie"].lower()


# ---------- 공개 경로 ----------

def test_health_is_public(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/login.html", "/login.js", "/style.css", "/app.js"])
def test_login_page_and_assets_are_public(client, path):
    assert client.get(path).status_code == 200


def test_session_status_without_cookie(client):
    res = client.get("/api/session")
    assert res.status_code == 200
    assert res.json() == {"authenticated": False}


# ---------- 로그인 ----------

def test_login_success(client):
    res = client.post("/api/session", json={"password": TEST_PASSWORD})
    assert res.status_code == 200
    assert res.json() == {"authenticated": True}

    cookie = set_cookie_header(res)
    assert cookie.startswith(f"{auth.COOKIE_NAME}=")
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie
    assert f"max-age={30 * 24 * 60 * 60}" in cookie

    assert client.get("/api/session").json() == {"authenticated": True}


def test_login_wrong_password(client):
    res = client.post("/api/session", json={"password": "wrong"})
    assert res.status_code == 401
    assert "set-cookie" not in res.headers
    assert client.get("/api/session").json() == {"authenticated": False}


def test_cookie_defaults_for_server(client, monkeypatch):
    monkeypatch.delenv("TODO_COOKIE_PATH")
    monkeypatch.delenv("TODO_COOKIE_SECURE")
    cookie = set_cookie_header(client.post("/api/session", json={"password": TEST_PASSWORD}))
    assert "path=/todo/" in cookie
    assert "secure" in cookie


def test_session_days_from_env(client, monkeypatch):
    monkeypatch.setenv("TODO_SESSION_DAYS", "7")
    cookie = set_cookie_header(client.post("/api/session", json={"password": TEST_PASSWORD}))
    assert f"max-age={7 * 24 * 60 * 60}" in cookie


@pytest.mark.parametrize("missing", ["TODO_PASSWORD", "TODO_SESSION_SECRET"])
def test_login_refused_without_server_settings(client, monkeypatch, missing):
    monkeypatch.delenv(missing)
    res = client.post("/api/session", json={"password": ""})
    assert res.status_code == 503
    assert "set-cookie" not in res.headers


def test_lock_after_repeated_failures(client, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(auth, "limiter", auth.LoginLimiter(clock=lambda: now[0]))

    for _ in range(auth.MAX_FAILURES):
        assert client.post("/api/session", json={"password": "wrong"}).status_code == 401

    # 막힌 동안에는 맞는 비밀번호도 받지 않는다.
    res = client.post("/api/session", json={"password": TEST_PASSWORD})
    assert res.status_code == 429
    assert int(res.headers["retry-after"]) > 0

    now[0] += auth.LOCK_SECONDS + 1
    assert client.post("/api/session", json={"password": TEST_PASSWORD}).status_code == 200


def test_success_resets_failure_count(client):
    for _ in range(auth.MAX_FAILURES - 1):
        client.post("/api/session", json={"password": "wrong"})
    assert client.post("/api/session", json={"password": TEST_PASSWORD}).status_code == 200
    assert client.post("/api/session", json={"password": "wrong"}).status_code == 401


# ---------- 인증 없는 요청 ----------

@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/todos"),
        ("POST", "/api/todos"),
        ("PATCH", "/api/todos/1"),
        ("DELETE", "/api/todos/1"),
        ("POST", "/api/todos/clear-done"),
        ("GET", "/api/anything"),
    ],
)
def test_api_without_login_is_401(client, method, path):
    res = client.request(method, path, json={"text": "몰래 추가", "done": True})
    assert res.status_code == 401
    assert res.json() == {"detail": "로그인이 필요합니다."}


def test_nothing_is_saved_without_login(client, set_today):
    client.post("/api/todos", json={"text": "몰래 추가"})
    client.post("/api/session", json={"password": TEST_PASSWORD})
    assert client.get("/api/todos").json()["todos"] == []


def test_logout_requires_login(client):
    assert client.delete("/api/session").status_code == 401


@pytest.mark.parametrize("path", ["/", "/index.html", "/INDEX.HTML"])
def test_pages_without_login_redirect_to_login(client, path):
    res = client.get(path, follow_redirects=False)
    assert res.status_code == 303
    # nginx가 /todo/ 접두사를 떼므로 상대 주소여야 한다.
    assert res.headers["location"] == "login.html"


def test_tampered_cookie_is_rejected(client):
    token = auth.make_token(TEST_SECRET)
    client.cookies.set(auth.COOKIE_NAME, token[:-1] + ("0" if token[-1] != "0" else "1"))
    assert client.get("/api/todos").status_code == 401


def test_cookie_signed_with_other_secret_is_rejected(client):
    client.cookies.set(auth.COOKIE_NAME, auth.make_token("other-secret"))
    assert client.get("/api/todos").status_code == 401


def test_expired_cookie_is_rejected(client):
    issued = int(time.time()) - 31 * 24 * 60 * 60
    client.cookies.set(auth.COOKIE_NAME, auth.make_token(TEST_SECRET, issued_at=issued))
    assert client.get("/api/session").json() == {"authenticated": False}
    assert client.get("/api/todos").status_code == 401


# ---------- 로그인한 뒤 ----------

def test_pages_after_login(logged_in):
    home = logged_in.get("/")
    assert home.status_code == 200
    assert "<title>오늘 할 일</title>" in home.text


def test_api_after_login_passes_auth(logged_in):
    # 없는 경로는 401이 아니라 404여야 한다.
    assert logged_in.get("/api/nothing-here").status_code == 404


def test_logout(logged_in):
    res = logged_in.delete("/api/session")
    assert res.status_code == 200
    assert f"{auth.COOKIE_NAME}=" in res.headers["set-cookie"]
    assert logged_in.get("/api/session").json() == {"authenticated": False}
    assert logged_in.get("/api/todos").status_code == 401
