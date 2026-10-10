"""루틴(반복 할 일) API. 응답 형식은 docs/api.md."""

from __future__ import annotations

from datetime import date
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, field_validator, model_validator

from . import clock
from .store import Store
from .todos import Category, clean_text


class Rule(BaseModel):
    """반복 규칙. weekly는 days(0=월 ... 6=일), monthly는 day(1~31)가 필요하다."""

    type: Literal["daily", "weekly", "monthly"]
    days: Optional[List[int]] = None
    day: Optional[int] = None

    @model_validator(mode="after")
    def check_fields(self) -> "Rule":
        if self.type == "weekly":
            if not self.days:
                raise ValueError("요일을 하나 이상 골라 주세요.")
            if any(day < 0 or day > 6 for day in self.days):
                raise ValueError("요일은 0(월)부터 6(일)까지입니다.")
        if self.type == "monthly" and (self.day is None or self.day < 1 or self.day > 31):
            raise ValueError("날짜는 1일부터 31일까지입니다.")
        return self

    def to_dict(self) -> dict[str, Any]:
        """저장하고 돌려주는 모양. 규칙에 필요 없는 값은 버린다."""
        if self.type == "weekly":
            return {"type": "weekly", "days": sorted(set(self.days or []))}
        if self.type == "monthly":
            return {"type": "monthly", "day": self.day}
        return {"type": "daily"}


class RoutineCreate(BaseModel):
    text: str
    category: Category = "work"
    rule: Rule

    @field_validator("text")
    @classmethod
    def check_text(cls, value: str) -> str:
        return clean_text(value)


class RoutineUpdate(BaseModel):
    text: Optional[str] = None
    category: Optional[Category] = None
    rule: Optional[Rule] = None

    @field_validator("text")
    @classmethod
    def check_text(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else clean_text(value)


router = APIRouter()


def _store(request: Request) -> Store:
    return request.app.state.store


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="루틴을 찾을 수 없습니다.")


def _log_day(day: str) -> str:
    """기록할 날짜를 확인한다. 날짜 모양이 아니거나 내일 이후면 422."""
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=422, detail="날짜는 YYYY-MM-DD로 적어 주세요.") from None
    normalized = parsed.isoformat()
    if normalized != day:
        raise HTTPException(status_code=422, detail="날짜는 YYYY-MM-DD로 적어 주세요.")
    if normalized > clock.today():
        raise HTTPException(status_code=422, detail="아직 오지 않은 날은 기록할 수 없습니다.")
    return normalized


def _set_log(request: Request, routine_id: int, day: str, done: bool) -> Response:
    result = _store(request).set_routine_log(routine_id, _log_day(day), done)
    if result == "not_found":
        raise _not_found()
    if result == "not_due":
        raise HTTPException(status_code=422, detail="그날은 이 루틴을 하는 날이 아닙니다.")
    return Response(status_code=204)


@router.get("/api/routines")
def list_routines(request: Request) -> dict:
    day = clock.today()
    return {"today": day, "routines": _store(request).list_routines(day)}


@router.post("/api/routines", status_code=201)
def add_routine(body: RoutineCreate, request: Request) -> dict:
    return _store(request).add_routine(body.text, body.category, body.rule.to_dict(), clock.today())


@router.patch("/api/routines/{routine_id}")
def update_routine(routine_id: int, body: RoutineUpdate, request: Request) -> dict:
    routine = _store(request).update_routine(
        routine_id,
        clock.today(),
        text=body.text,
        category=body.category,
        rule=body.rule.to_dict() if body.rule else None,
    )
    if routine is None:
        raise _not_found()
    return routine


@router.post("/api/routines/{routine_id}/end", status_code=204)
def end_routine(routine_id: int, request: Request) -> Response:
    if not _store(request).end_routine(routine_id, clock.today()):
        raise _not_found()
    return Response(status_code=204)


@router.put("/api/routines/{routine_id}/logs/{day}", status_code=204)
def mark_done(routine_id: int, day: str, request: Request) -> Response:
    return _set_log(request, routine_id, day, True)


@router.delete("/api/routines/{routine_id}/logs/{day}", status_code=204)
def unmark_done(routine_id: int, day: str, request: Request) -> Response:
    return _set_log(request, routine_id, day, False)
