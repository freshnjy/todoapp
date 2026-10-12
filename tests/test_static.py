"""화면 파일이 그대로 내려오고, `/todo/` 접두사 아래에서도 깨지지 않는지 확인한다."""

import re
from pathlib import Path

import pytest

from backend.app.main import FRONTEND_DIR


def test_index_is_served_at_root(logged_in):
    res = logged_in.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "<title>오늘 할 일</title>" in res.text


@pytest.mark.parametrize("name", ["index.html", "login.html", "style.css", "app.js", "habits.js", "memos.js", "voice.js", "login.js"])
def test_frontend_files_are_served(logged_in, name):
    res = logged_in.get(f"/{name}")
    assert res.status_code == 200
    assert res.content == (FRONTEND_DIR / name).read_bytes()


def test_static_files_are_revalidated(client):
    assert client.get("/app.js").headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_docs_are_off(logged_in, path):
    assert logged_in.get(path).status_code == 404


def test_unknown_path_is_404(logged_in):
    assert logged_in.get("/no-such-file.html").status_code == 404


@pytest.mark.parametrize("path", sorted(FRONTEND_DIR.glob("*.html")), ids=lambda p: p.name)
def test_html_uses_relative_addresses(path: Path):
    """nginx가 /todo/ 접두사를 떼므로, /로 시작하는 주소는 다른 앱(투자 대시보드)으로 간다."""
    addresses = re.findall(r'(?:href|src|action)="([^"]*)"', path.read_text(encoding="utf-8"))
    assert addresses, "주소가 하나도 없으면 검사가 의미 없다"
    assert [a for a in addresses if a.startswith("/")] == []


@pytest.mark.parametrize("path", sorted(FRONTEND_DIR.glob("*.js")), ids=lambda p: p.name)
def test_scripts_use_relative_addresses(path: Path):
    script = path.read_text(encoding="utf-8")
    assert re.findall(r"""fetch\(\s*['"`]/""", script) == []
    assert re.findall(r"""api\(\s*'[A-Z]+',\s*['"`]/""", script) == []
    assert re.findall(r"""location\.(?:href\s*=|replace\()\s*['"`]/""", script) == []


def test_todos_are_not_kept_in_the_browser():
    """할 일은 서버에만 저장한다 (기기마다 목록이 달라지지 않게)."""
    script = (FRONTEND_DIR / "app.js").read_text(encoding="utf-8")
    assert "localStorage" not in script


def test_add_form_keeps_only_one_row_outside_the_folding_part():
    """입력 영역은 접힌 채로 시작하고, 카테고리·반복·묶음 버튼은 접히는 덩어리 안에 있다."""
    page = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    form = page[page.index('id="add-form"'):page.index("</form>")]
    assert 'class="card add-form is-collapsed"' in page
    head, more = form.split('id="add-more"')
    for control in ('id="add-input"', 'id="voice-btn"', 'type="submit"'):
        assert control in head
    for control in ('id="add-category"', 'id="add-rule"', 'id="group-bar"', 'id="group-new"'):
        assert control in more and control not in head


def test_stats_card_has_no_category_rows():
    page = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    script = (FRONTEND_DIR / "app.js").read_text(encoding="utf-8")
    assert "stats-list" not in page and "stats-row" not in page
    assert "stats-list" not in script
