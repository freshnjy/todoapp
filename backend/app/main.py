"""할 일 앱.

nginx가 `/todo/` 접두사를 떼고 넘겨주므로 앱 안의 경로는 `/`부터 시작한다.
1-1단계에서는 화면 파일만 내려 준다. 로그인과 저장 API는 1-2단계에서 추가한다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


class RevalidatingStaticFiles(StaticFiles):
    """정적 파일은 매번 서버에 확인(ETag)하게 한다.

    빌드 단계가 없어 파일 이름에 버전이 없으므로, 이게 없으면 브라우저가 화면 파일을
    한동안 그대로 써서 배포한 새 버전이 늦게 보인다.
    """

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app = FastAPI(title="할 일", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


app.mount("/", RevalidatingStaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
