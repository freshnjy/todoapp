"""1-1단계: 화면 파일이 그대로 내려오고, `/todo/` 접두사 아래에서도 깨지지 않는지 확인한다."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import FRONTEND_DIR, app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_index_is_served_at_root(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "<title>오늘 할 일</title>" in res.text


@pytest.mark.parametrize("name", ["index.html", "style.css", "app.js"])
def test_frontend_files_are_served(client, name):
    res = client.get(f"/{name}")
    assert res.status_code == 200
    assert res.content == (FRONTEND_DIR / name).read_bytes()


def test_static_files_are_revalidated(client):
    assert client.get("/app.js").headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_docs_are_off(client, path):
    assert client.get(path).status_code == 404


def test_unknown_path_is_404(client):
    assert client.get("/no-such-file.html").status_code == 404


@pytest.mark.parametrize("path", sorted(FRONTEND_DIR.glob("*.html")), ids=lambda p: p.name)
def test_html_uses_relative_addresses(path: Path):
    """nginx가 /todo/ 접두사를 떼므로, /로 시작하는 주소는 다른 앱(투자 대시보드)으로 간다."""
    addresses = re.findall(r'(?:href|src|action)="([^"]*)"', path.read_text(encoding="utf-8"))
    assert addresses, "주소가 하나도 없으면 검사가 의미 없다"
    assert [a for a in addresses if a.startswith("/")] == []


def test_script_does_not_call_absolute_paths():
    script = (FRONTEND_DIR / "app.js").read_text(encoding="utf-8")
    assert re.findall(r"""fetch\(\s*['"`]/""", script) == []
