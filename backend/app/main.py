"""할 일 앱.

nginx가 `/todo/` 접두사를 떼고 넘겨주므로 앱 안의 경로는 `/`부터 시작한다.
리디렉션 주소는 상대 경로로 써서 접두사가 있어도 없어도 동작하게 한다.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import auth, groups, habits, routines, todos
from .store import Store

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

# 로그인 없이 받을 수 있는 정적 파일. 화면(HTML)은 login.html만 공개한다.
PUBLIC_PAGES = {"/login.html"}
PUBLIC_ASSET_SUFFIXES = (".css", ".js", ".png", ".svg", ".ico")


class RevalidatingStaticFiles(StaticFiles):
    """정적 파일은 매번 서버에 확인(ETag)하게 한다.

    빌드 단계가 없어 파일 이름에 버전이 없으므로, 이게 없으면 브라우저가 화면 파일을
    한동안 그대로 써서 배포한 새 버전이 늦게 보인다.
    """

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = Store.from_env()
    yield


app = FastAPI(title="할 일", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


def is_public(method: str, path: str) -> bool:
    path = path.lower()
    if path == "/api/health":
        return True
    if path == "/api/session":
        return method != "DELETE"
    if path.startswith("/api"):
        return False
    return path in PUBLIC_PAGES or path.endswith(PUBLIC_ASSET_SUFFIXES)


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if is_public(request.method, path) or auth.is_authenticated(request):
        return await call_next(request)
    if path.lower().startswith("/api"):
        return JSONResponse({"detail": "로그인이 필요합니다."}, status_code=401)
    return RedirectResponse("login.html", status_code=303)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(todos.router)
app.include_router(groups.router)
app.include_router(routines.router)
app.include_router(habits.router)

app.mount("/", RevalidatingStaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
