"""반복 규칙이 어느 날짜에 해당하는지."""

from datetime import date

import pytest

from backend.app.rules import is_due

# 2026-10-05는 월요일이다.
MONDAY = date(2026, 10, 5)


def week():
    return [date(2026, 10, 5 + offset) for offset in range(7)]  # 월 ~ 일


def test_daily_is_due_every_day():
    assert all(is_due({"type": "daily"}, day) for day in week())


def test_weekly_is_due_only_on_chosen_days():
    rule = {"type": "weekly", "days": [0, 2, 4]}  # 월, 수, 금
    assert [is_due(rule, day) for day in week()] == [True, False, True, False, True, False, False]


def test_weekly_weekend():
    rule = {"type": "weekly", "days": [5, 6]}
    assert [is_due(rule, day) for day in week()] == [False] * 5 + [True, True]


def test_monthly_is_due_on_that_day_only():
    rule = {"type": "monthly", "day": 25}
    assert is_due(rule, date(2026, 10, 25))
    assert not is_due(rule, date(2026, 10, 24))
    assert not is_due(rule, date(2026, 10, 26))
    assert is_due(rule, date(2026, 11, 25))


@pytest.mark.parametrize(
    ("day_of_month", "due", "not_due"),
    [
        (31, date(2026, 10, 31), date(2026, 10, 30)),  # 31일이 있는 달
        (31, date(2026, 11, 30), date(2026, 11, 29)),  # 30일까지인 달은 30일에
        (31, date(2026, 2, 28), date(2026, 2, 27)),  # 평년 2월은 28일에
        (30, date(2026, 2, 28), date(2026, 2, 27)),
        (29, date(2028, 2, 29), date(2028, 2, 28)),  # 윤년 2월
        (29, date(2026, 2, 28), date(2026, 2, 27)),
    ],
)
def test_monthly_uses_last_day_when_the_month_is_short(day_of_month, due, not_due):
    rule = {"type": "monthly", "day": day_of_month}
    assert is_due(rule, due)
    assert not is_due(rule, not_due)


def test_monthly_is_due_once_in_a_short_month():
    rule = {"type": "monthly", "day": 31}
    february = [date(2026, 2, day) for day in range(1, 29)]
    assert sum(is_due(rule, day) for day in february) == 1


def test_unknown_rule_is_never_due():
    assert not is_due({"type": "yearly"}, MONDAY)
