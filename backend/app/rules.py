"""반복 규칙. "이 규칙이 이 날짜에 해당하는가"를 여기 한 곳에서 판단한다.

규칙의 모양 (docs/api.md):
    {"type": "daily"}
    {"type": "weekly", "days": [0, 2, 4]}    # 0=월 ... 6=일
    {"type": "monthly", "day": 25}           # 1~31
"""

from __future__ import annotations

import calendar
from datetime import date
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
