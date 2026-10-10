"""자체 로그인: 비밀번호 확인, 서명된 기기 쿠키, 로그인 실패 제한.

JY Bridge와 같은 방식이다. 쿠키 값은 `발급시각.서명` 형태다. 서명은 TODO_SESSION_SECRET으로 만든
HMAC-SHA256이고, 서버에는 세션을 저장하지 않는다. 비밀 값을 바꾸면 모든 기기가 다시 로그인해야 한다.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

COOKIE_NAME = "todo_session"
DEFAULT_SESSION_DAYS = 30
DEFAULT_COOKIE_PATH = "/todo/"
MAX_FAILURES = 5
LOCK_SECONDS = 60


@dataclass(frozen=True)
class Settings:
    password: str
    session_secret: str
    session_days: int
    cookie_path: str
    cookie_secure: bool

    @property
    def max_age(self) -> int:
        return self.session_days * 24 * 60 * 60


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value not in {"0", "false", "no", "off"}


def get_settings() -> Settings:
    """환경 변수를 요청마다 읽는다."""
    return Settings(
        password=os.environ.get("TODO_PASSWORD", ""),
        session_secret=os.environ.get("TODO_SESSION_SECRET", ""),
        session_days=_env_int("TODO_SESSION_DAYS", DEFAULT_SESSION_DAYS),
        cookie_path=os.environ.get("TODO_COOKIE_PATH", "").strip() or DEFAULT_COOKIE_PATH,
        cookie_secure=_env_bool("TODO_COOKIE_SECURE", True),
    )


def _sign(secret: str, issued_at: int) -> str:
    message = f"todo-session.{issued_at}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def make_token(secret: str, issued_at: int | None = None) -> str:
    issued = int(time.time()) if issued_at is None else issued_at
    return f"{issued}.{_sign(secret, issued)}"


def verify_token(token: str, secret: str, max_age: int, now: float | None = None) -> bool:
    if not token or not secret:
        return False
    issued_text, _, signature = token.partition(".")
    if not issued_text.isdigit() or not signature:
        return False
    issued = int(issued_text)
    current = time.time() if now is None else now
    # 시계가 조금 어긋나는 것은 허용하되, 먼 미래에 발급된 값은 받지 않는다.
    if issued > current + 300 or current - issued > max_age:
        return False
    return secrets.compare_digest(signature.encode(), _sign(secret, issued).encode())


def is_authenticated(request: Request) -> bool:
    settings = get_settings()
    token = request.cookies.get(COOKIE_NAME, "")
    return verify_token(token, settings.session_secret, settings.max_age)


def password_matches(given: str, expected: str) -> bool:
    if not expected:
        return False
    return secrets.compare_digest(given.encode(), expected.encode())


class LoginLimiter:
    """연속 실패가 MAX_FAILURES번이면 LOCK_SECONDS 동안 로그인을 막는다.

    혼자 쓰는 서비스라 IP별로 나누지 않고 전체에 하나만 둔다.
    """

    def __init__(
        self,
        max_failures: int = MAX_FAILURES,
        lock_seconds: int = LOCK_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_failures = max_failures
        self.lock_seconds = lock_seconds
        self.clock = clock
        self.failures = 0
        self.locked_until = 0.0

    def seconds_left(self) -> int:
        left = self.locked_until - self.clock()
        return int(left) + 1 if left > 0 else 0

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.max_failures:
            self.failures = 0
            self.locked_until = self.clock() + self.lock_seconds

    def reset(self) -> None:
        self.failures = 0
        self.locked_until = 0.0


limiter = LoginLimiter()

router = APIRouter()


class LoginRequest(BaseModel):
    password: str


def _cookie_options(settings: Settings) -> dict:
    return {
        "path": settings.cookie_path,
        "secure": settings.cookie_secure,
        "httponly": True,
        "samesite": "lax",
    }


@router.post("/api/session")
async def login(body: LoginRequest, response: Response) -> dict:
    settings = get_settings()
    if not settings.password or not settings.session_secret:
        raise HTTPException(status_code=503, detail="서버에 로그인 설정이 없습니다.")

    wait = limiter.seconds_left()
    if wait:
        raise HTTPException(
            status_code=429,
            detail="잠시 후 다시 시도해 주세요.",
            headers={"Retry-After": str(wait)},
        )

    if not password_matches(body.password, settings.password):
        limiter.record_failure()
        raise HTTPException(status_code=401, detail="비밀번호가 맞지 않습니다.")

    limiter.reset()
    response.set_cookie(
        COOKIE_NAME,
        make_token(settings.session_secret),
        max_age=settings.max_age,
        **_cookie_options(settings),
    )
    return {"authenticated": True}


@router.get("/api/session")
async def session_status(request: Request) -> dict:
    return {"authenticated": is_authenticated(request)}


@router.delete("/api/session")
async def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME, **_cookie_options(get_settings()))
    return {"authenticated": False}
