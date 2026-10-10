"""할 일 API. 응답 형식은 docs/api.md."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, field_validator

from .store import Store

MAX_LENGTH = 100
Category = Literal["work", "personal", "growth"]

# 한국은 서머타임이 없어 고정 +09:00으로 둔다 (Windows에는 시간대 자료가 없을 수 있다).
KST = timezone(timedelta(hours=9))


def today() -> str:
    """서버가 보는 오늘 (Asia/Seoul, YYYY-MM-DD). 기기 시계에 맡기지 않는다."""
    return datetime.now(KST).date().isoformat()


def _clean_text(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("할 일 내용을 입력해 주세요.")
    if len(value) > MAX_LENGTH:
        raise ValueError(f"할 일은 {MAX_LENGTH}자까지 쓸 수 있습니다.")
    return value


class TodoCreate(BaseModel):
    text: str
    category: Category = "work"

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return _clean_text(value)


class TodoUpdate(BaseModel):
    text: Optional[str] = None
    category: Optional[Category] = None
    done: Optional[bool] = None

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else _clean_text(value)


router = APIRouter()


def _store(request: Request) -> Store:
    return request.app.state.store


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="할 일을 찾을 수 없습니다.")


@router.get("/api/todos")
def list_todos(request: Request) -> dict:
    day = today()
    return {"today": day, "todos": _store(request).list_todos(day)}


@router.post("/api/todos", status_code=201)
def add_todo(body: TodoCreate, request: Request) -> dict:
    return _store(request).add_todo(body.text, body.category)


# {todo_id} 경로보다 먼저 등록한다.
@router.post("/api/todos/clear-done")
def clear_done(request: Request) -> dict:
    return {"deleted": _store(request).clear_done()}


@router.patch("/api/todos/{todo_id}")
def update_todo(todo_id: int, body: TodoUpdate, request: Request) -> dict:
    todo = _store(request).update_todo(
        todo_id, today(), text=body.text, category=body.category, done=body.done
    )
    if todo is None:
        raise _not_found()
    return todo


@router.delete("/api/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int, request: Request) -> Response:
    if not _store(request).delete_todo(todo_id):
        raise _not_found()
    return Response(status_code=204)
