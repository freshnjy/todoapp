"""서버가 보는 날짜. "오늘"은 기기 시계가 아니라 여기서 정한다."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# 한국은 서머타임이 없어 고정 +09:00으로 둔다 (Windows에는 시간대 자료가 없을 수 있다).
KST = timezone(timedelta(hours=9))


def today() -> str:
    """오늘 (Asia/Seoul, YYYY-MM-DD)."""
    return datetime.now(KST).date().isoformat()


def now() -> str:
    """지금 (Asia/Seoul, 초까지). 예: 2026-10-12T21:40:05+09:00. 앞 10자가 그날의 날짜다."""
    return datetime.now(KST).isoformat(timespec="seconds")
