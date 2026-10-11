"""묶음 API. 장보기처럼 품목이 여러 개인 것을 담는 틀. 응답 형식은 docs/api.md."""

from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, field_validator

from .store import Store
from .todos import MAX_LENGTH, Category

NAME_MAX_LENGTH = 20
# 한 번에 넣는 글 전체의 길이와 품목 수
ITEMS_TEXT_MAX_LENGTH = 1000
ITEMS_MAX_COUNT = 30

# 쉼표(,)와 전각 쉼표(，、)로 나눈다.
_SEPARATORS = re.compile(r"[,，、]")


def clean_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("묶음 이름을 입력해 주세요.")
    if len(value) > NAME_MAX_LENGTH:
        raise ValueError(f"묶음 이름은 {NAME_MAX_LENGTH}자까지 쓸 수 있습니다.")
    return value


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


class GroupCreate(BaseModel):
    name: str
    category: Category = "personal"

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        return clean_name(value)


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[Category] = None

    @field_validator("name")
    @classmethod
    def check_name(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else clean_name(value)


class ItemsCreate(BaseModel):
    text: str


router = APIRouter()


def _store(request: Request) -> Store:
    return request.app.state.store


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="묶음을 찾을 수 없습니다.")


@router.get("/api/groups")
def list_groups(request: Request) -> dict:
    return {"groups": _store(request).list_groups()}


@router.post("/api/groups", status_code=201)
def add_group(body: GroupCreate, request: Request) -> dict:
    return _store(request).add_group(body.name, body.category)


@router.patch("/api/groups/{group_id}")
def update_group(group_id: int, body: GroupUpdate, request: Request) -> dict:
    group = _store(request).update_group(group_id, name=body.name, category=body.category)
    if group is None:
        raise _not_found()
    return group


@router.delete("/api/groups/{group_id}", status_code=204)
def delete_group(group_id: int, request: Request) -> Response:
    if not _store(request).delete_group(group_id):
        raise _not_found()
    return Response(status_code=204)


@router.post("/api/groups/{group_id}/items", status_code=201)
def add_items(group_id: int, body: ItemsCreate, request: Request) -> dict:
    try:
        texts = split_items(body.text)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    items = _store(request).add_items(group_id, texts)
    if items is None:
        raise _not_found()
    return {"todos": items}
