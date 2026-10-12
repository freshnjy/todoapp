"""JY Bridge용 요약 API. 응답 형식은 docs/api.md의 "JY Bridge용 요약".

Bridge가 서버 안에서 부르는 조회 전용 경로다. 로그인 쿠키가 아니라 전용 토큰(TODO_BRIDGE_TOKEN)만 본다.
이 토큰은 이 경로에서만 통하고, 여기서는 아무것도 지우거나 고치지 않는다.
"""

from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, HTTPException, Request

from . import clock
from .store import Store

PATH = "/api/bridge-summary"
MAX_NAMES = 10

router = APIRouter()


def token_matches(header: str, expected: str) -> bool:
    """Authorization 헤더가 `Bearer {토큰}`이고 값이 맞는지. 토큰 설정이 비어 있으면 늘 거짓이다."""
    if not expected:
        return False
    scheme, _, given = header.partition(" ")
    if scheme.lower() != "bearer":
        return False
    return secrets.compare_digest(given.strip().encode(), expected.encode())


@router.get(PATH)
async def bridge_summary(request: Request) -> dict:
    expected = os.environ.get("TODO_BRIDGE_TOKEN", "").strip()
    if not token_matches(request.headers.get("authorization", ""), expected):
        raise HTTPException(status_code=401, detail="토큰이 필요합니다.")
    store: Store = request.app.state.store
    return store.bridge_summary(clock.today(), MAX_NAMES)
