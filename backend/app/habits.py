"""해빗트래커 API: 기간의 루틴별 날짜 상태, 연속 달성일, 달성 수. 응답 형식은 docs/api.md.

체크와 해제는 루틴 API(`api/routines/{id}/logs/{날짜}`)를 그대로 쓴다.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request

from . import clock

# 한 번에 볼 수 있는 가장 긴 기간(일). 화면은 한 주 또는 한 달만 묻는다.
MAX_DAYS = 62

router = APIRouter()


def _parse(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="날짜는 YYYY-MM-DD로 적어 주세요.") from None
    if parsed.isoformat() != value:
        raise HTTPException(status_code=422, detail="날짜는 YYYY-MM-DD로 적어 주세요.")
    return parsed


@router.get("/api/habits")
def habits(start: str, end: str, request: Request) -> dict:
    first, last = _parse(start), _parse(end)
    if first > last:
        raise HTTPException(status_code=422, detail="시작일이 종료일보다 뒤에 있습니다.")
    if (last - first).days + 1 > MAX_DAYS:
        raise HTTPException(status_code=422, detail=f"한 번에 {MAX_DAYS}일까지 볼 수 있습니다.")
    today = clock.today()
    return {
        "today": today,
        "start": start,
        "end": end,
        "routines": request.app.state.store.habits(start, end, today),
    }
