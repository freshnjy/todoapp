"""할 일 API. 응답 형식은 docs/api.md."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, field_validator

from . import clock
from .store import MemoError, Store

MAX_LENGTH = 100
Category = Literal["work", "personal", "growth"]

def clean_text(value: str) -> str:
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
    def check_text(cls, value: str) -> str:
        return clean_text(value)


class TodoUpdate(BaseModel):
    text: Optional[str] = None
    category: Optional[Category] = None
    done: Optional[bool] = None

    @field_validator("text")
    @classmethod
    def check_text(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else clean_text(value)


class TodoMemos(BaseModel):
    # 이 할 일에 붙일 메모 id 전부 (빈 목록이면 모두 뗀다)
    memo_ids: list[int]


router = APIRouter()


def _store(request: Request) -> Store:
    return request.app.state.store


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="할 일을 찾을 수 없습니다.")


@router.get("/api/todos")
def list_todos(request: Request) -> dict:
    day = clock.today()
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
        todo_id, clock.today(), text=body.text, category=body.category, done=body.done
    )
    if todo is None:
        raise _not_found()
    return todo


@router.put("/api/todos/{todo_id}/memos")
def set_todo_memos(todo_id: int, body: TodoMemos, request: Request) -> dict:
    """할 일에 붙인 메모를 통째로 바꾼다 (10단계). 메모는 그대로 두고 연결만 바꾼다."""
    try:
        todo = _store(request).set_todo_memos(todo_id, body.memo_ids)
    except MemoError as error:
        raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다.") from error
    if todo is None:
        raise _not_found()
    return todo


@router.delete("/api/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int, request: Request) -> Response:
    if not _store(request).delete_todo(todo_id):
        raise _not_found()
    return Response(status_code=204)
