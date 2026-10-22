"""저장소(메모) API. 그때그때 생각난 것을 남겨 두는 곳. 응답 형식은 docs/api.md.

메모는 할 일과 따로 산다. 날짜가 바뀌어도 지우지 않고, 체크한 품목도 표시만 남긴다.
"""

from __future__ import annotations

from typing import Optional

import re

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, field_validator

from . import clock
from .store import MemoError, Store
from .todos import MAX_LENGTH

TITLE_MAX_LENGTH = 20
BODY_MAX_LENGTH = 2000
# 한 번에 넣는 품목 글 전체의 길이와 품목 수 (조각 하나는 MAX_LENGTH)
ITEMS_TEXT_MAX_LENGTH = 1000
ITEMS_MAX_COUNT = 30

# 쉼표(,)와 전각 쉼표(，、)로 나눈다.
_SEPARATORS = re.compile(r"[,，、]")


def split_items(value: str) -> list[str]:
    """쉼표로 나눠 품목 목록을 만든다. 앞뒤 공백을 떼고 빈 조각은 버린다."""
    if len(value) > ITEMS_TEXT_MAX_LENGTH:
        raise ValueError(f"한 번에 {ITEMS_TEXT_MAX_LENGTH}자까지 넣을 수 있습니다.")
    items = [piece.strip() for piece in _SEPARATORS.split(value)]
    items = [piece for piece in items if piece]
    if not items:
        raise ValueError("품목을 입력해 주세요.")
    if len(items) > ITEMS_MAX_COUNT:
        raise ValueError(f"한 번에 {ITEMS_MAX_COUNT}개까지 넣을 수 있습니다.")
    if any(len(piece) > MAX_LENGTH for piece in items):
        raise ValueError(f"품목 하나는 {MAX_LENGTH}자까지 쓸 수 있습니다.")
    return items

_MEMO_ERRORS = {
    "duplicate": (409, "같은 제목의 메모가 있습니다."),
    "empty": (422, "제목, 글, 품목 중 하나는 적어 주세요."),
}


def clean_title(value: Optional[str]) -> Optional[str]:
    """앞뒤 공백을 뗀다. 비면 None(제목 없음)."""
    if value is None:
        return None
    value = value.strip()
    if len(value) > TITLE_MAX_LENGTH:
        raise ValueError(f"제목은 {TITLE_MAX_LENGTH}자까지 쓸 수 있습니다.")
    return value or None


def clean_body(value: Optional[str]) -> str:
    """끝의 빈 줄과 공백을 뗀다 (줄 안의 들여쓰기는 둔다)."""
    value = (value or "").rstrip()
    if len(value) > BODY_MAX_LENGTH:
        raise ValueError(f"글은 {BODY_MAX_LENGTH}자까지 쓸 수 있습니다.")
    return value


def clean_item(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("품목을 입력해 주세요.")
    if len(value) > MAX_LENGTH:
        raise ValueError(f"품목 하나는 {MAX_LENGTH}자까지 쓸 수 있습니다.")
    return value


class MemoCreate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    # 쉼표로 나눠 여러 품목을 만든다. 비워 두면 품목 없이 만든다
    items: Optional[str] = None

    @field_validator("title")
    @classmethod
    def check_title(cls, value: Optional[str]) -> Optional[str]:
        return clean_title(value)

    @field_validator("body")
    @classmethod
    def check_body(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else clean_body(value)


class MemoUpdate(BaseModel):
    # 보낸 것만 바꾼다. title에 null이나 빈 글을 보내면 제목을 지운다
    title: Optional[str] = None
    body: Optional[str] = None

    @field_validator("title")
    @classmethod
    def check_title(cls, value: Optional[str]) -> Optional[str]:
        return clean_title(value)

    @field_validator("body")
    @classmethod
    def check_body(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else clean_body(value)


class ItemsCreate(BaseModel):
    text: str


class ItemUpdate(BaseModel):
    text: Optional[str] = None
    done: Optional[bool] = None

    @field_validator("text")
    @classmethod
    def check_text(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else clean_item(value)


router = APIRouter()


def _store(request: Request) -> Store:
    return request.app.state.store


def _not_found(what: str = "메모") -> HTTPException:
    return HTTPException(status_code=404, detail=f"{what}를 찾을 수 없습니다.")


def _memo_error(error: MemoError) -> HTTPException:
    status, detail = _MEMO_ERRORS[error.reason]
    return HTTPException(status_code=status, detail=detail)


def _split(text: str) -> list[str]:
    try:
        return split_items(text)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/api/memos")
def list_memos(request: Request) -> dict:
    return {"memos": _store(request).list_memos()}


@router.post("/api/memos", status_code=201)
def add_memo(body: MemoCreate, request: Request) -> dict:
    items = _split(body.items) if body.items and body.items.strip() else []
    try:
        return _store(request).add_memo(body.title, body.body or "", items, clock.now())
    except MemoError as error:
        raise _memo_error(error) from error


@router.patch("/api/memos/{memo_id}")
def update_memo(memo_id: int, body: MemoUpdate, request: Request) -> dict:
    changes = {name: getattr(body, name) for name in body.model_fields_set}
    if "body" in changes and changes["body"] is None:
        changes["body"] = ""
    try:
        memo = _store(request).update_memo(memo_id, clock.now(), **changes)
    except MemoError as error:
        raise _memo_error(error) from error
    if memo is None:
        raise _not_found()
    return memo


@router.delete("/api/memos/{memo_id}", status_code=204)
def delete_memo(memo_id: int, request: Request) -> Response:
    if not _store(request).delete_memo(memo_id):
        raise _not_found()
    return Response(status_code=204)


@router.post("/api/memos/{memo_id}/items", status_code=201)
def add_items(memo_id: int, body: ItemsCreate, request: Request) -> dict:
    memo = _store(request).add_memo_items(memo_id, _split(body.text), clock.now())
    if memo is None:
        raise _not_found()
    return memo


@router.patch("/api/memos/{memo_id}/items/{item_id}")
def update_item(memo_id: int, item_id: int, body: ItemUpdate, request: Request) -> dict:
    memo = _store(request).update_memo_item(memo_id, item_id, clock.now(), text=body.text, done=body.done)
    if memo is None:
        raise _not_found("품목")
    return memo


@router.delete("/api/memos/{memo_id}/items/{item_id}")
def delete_item(memo_id: int, item_id: int, request: Request) -> dict:
    memo = _store(request).delete_memo_item(memo_id, item_id, clock.now())
    if memo is None:
        raise _not_found("품목")
    return memo


@router.post("/api/memos/{memo_id}/clear-done")
def clear_done(memo_id: int, request: Request) -> dict:
    memo = _store(request).clear_memo_done(memo_id, clock.now())
    if memo is None:
        raise _not_found()
    return memo
