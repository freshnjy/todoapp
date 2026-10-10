"""반복 규칙. "이 규칙이 이 날짜에 해당하는가"를 여기 한 곳에서 판단한다.

규칙의 모양 (docs/api.md):
    {"type": "daily"}
    {"type": "weekly", "days": [0, 2, 4]}    # 0=월 ... 6=일
    {"type": "monthly", "day": 25}           # 1~31
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any


def is_due(rule: dict[str, Any], day: date) -> bool:
    kind = rule.get("type")
    if kind == "daily":
        return True
    if kind == "weekly":
        return day.weekday() in rule["days"]
    if kind == "monthly":
        # 그 달에 없는 날짜(예: 2월의 31일)는 그 달의 마지막 날로 본다.
        last_day = calendar.monthrange(day.year, day.month)[1]
        return day.day == min(rule["day"], last_day)
    return False


# ---------- 기간별 상태와 연속 달성일 (해빗트래커) ----------
#
# versions: 규칙의 이력. (적용 시작일 YYYY-MM-DD, 규칙)을 시작일 순으로 늘어놓은 것.
# created_on, ended_on: 루틴을 만든 날과 종료한 날(없으면 None). 종료한 날부터는 하는 날이 아니다.
# logs: 했다고 적은 날짜(YYYY-MM-DD)의 집합.

DONE = "done"  # 한 날
MISSED = "missed"  # 하는 날이었는데 안 한 지난 날
PENDING = "pending"  # 오늘이 하는 날이고 아직 안 했다
OFF = "off"  # 하는 날이 아니다 (쉬는 날, 만들기 전, 종료한 뒤)
UPCOMING = "upcoming"  # 아직 오지 않은 하는 날


def rule_on(versions: list[tuple[str, dict[str, Any]]], day: str) -> dict[str, Any] | None:
    """그 날짜에 쓰던 규칙. 첫 규칙보다 앞선 날짜면 None."""
    found = None
    for start_on, rule in versions:
        if start_on > day:
            break
        found = rule
    return found


def is_due_on(
    versions: list[tuple[str, dict[str, Any]]],
    created_on: str,
    ended_on: str | None,
    day: date,
) -> bool:
    """루틴이 살아 있던 날이고, 그날의 규칙으로 하는 날이었는지."""
    text = day.isoformat()
    if text < created_on or (ended_on is not None and text >= ended_on):
        return False
    rule = rule_on(versions, text)
    return rule is not None and is_due(rule, day)


def day_statuses(
    versions: list[tuple[str, dict[str, Any]]],
    created_on: str,
    ended_on: str | None,
    logs: set[str],
    start: date,
    end: date,
    today: date,
) -> list[str]:
    """start부터 end까지 하루씩의 상태."""
    statuses = []
    day = start
    while day <= end:
        if not is_due_on(versions, created_on, ended_on, day):
            statuses.append(OFF)
        elif day > today:
            statuses.append(UPCOMING)
        elif day.isoformat() in logs:
            statuses.append(DONE)
        elif day == today:
            statuses.append(PENDING)
        else:
            statuses.append(MISSED)
        day += timedelta(days=1)
    return statuses


def streak(
    versions: list[tuple[str, dict[str, Any]]],
    created_on: str,
    ended_on: str | None,
    logs: set[str],
    today: date,
) -> int:
    """오늘까지 이어진 연속 달성일.

    쉬는 날은 건너뛴다 (끊기지 않는다). 오늘이 하는 날인데 아직 안 했으면 어제까지의 연속을 유지하고,
    오늘 하면 하루가 더해진다. 하는 날이었는데 안 한 지난 날에서 끊긴다. 종료한 루틴은 0.
    """
    if ended_on is not None and ended_on <= today.isoformat():
        return 0
    count = 0
    day = today
    first = date.fromisoformat(created_on)
    while day >= first:
        if is_due_on(versions, created_on, ended_on, day):
            if day.isoformat() in logs:
                count += 1
            elif day != today:
                break
        day -= timedelta(days=1)
    return count
