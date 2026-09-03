"""The one observation metric, and the only place it is computed.

T07-C13, C14 and C15 ask that the before/after comparison use the same metric,
the same unit and the same calculation rule. The way to be able to show that is
not to be careful twice -- it is to have one function, so that "the same" is
true by construction and a reviewer can read the whole of it in one screen.

Fixed on day 1 and unchanged for the five days (C05, C06, C08):

    지표   하루 계획 대비 실제 비율
    단위   배
    계산   실제분 ÷ 예상분
    반올림 소수 둘째 자리, 반올림(half-up)

Where the numbers come from, in Asia/Seoul (C27's week and every day boundary
in this app are Seoul days):

    예상분  that day's tasks (due_date == the day), soft-deleted ones excluded
    실제분  execution records started that day, on this plan's tasks

The exclusions are the study protocol's, written here because a rule that lives
only in a document is a rule the code can disagree with:

  - 결측 (C23) — a day with 예상분 = 0 has no ratio. Not 0, not 1: `None`.
    Dividing by nothing is not a result, and calling it one would put a made-up
    point in the middle of a five-day comparison.
  - 중복 (C24) — execution records are individually meaningful (start, end,
    blocker), so two entries for one task are two entries. Nothing is
    de-duplicated, and the record count is reported so anyone can see it.
  - 이상값 (C25) — nothing is dropped. Five days is too few for an outlier rule
    to be anything but a way to delete an inconvenient day; a day that looks
    wrong is a day to explain.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.extensions import db
from app.models import ExecutionLog, Task

SEOUL = ZoneInfo("Asia/Seoul")

METRIC_KEY = "dailyPlannedVsActual"
METRIC_NAME = "하루 계획 대비 실제 비율"
METRIC_UNIT = "배"
METRIC_FORMULA = "실제분 ÷ 예상분"
METRIC_ROUNDING = "소수 둘째 자리 반올림"
METRIC_TIMEZONE = "Asia/Seoul"

_PLACES = Decimal("0.01")


def ratio(estimated_minutes: int, actual_minutes: int) -> float | None:
    """실제분 ÷ 예상분, to two places. `None` when there is nothing to divide by.

    Decimal, not round(): Python rounds halves to even, so round(1.125, 2) is
    1.12 while the rule written in the protocol -- and the one a reader checking
    the arithmetic by hand will apply -- gives 1.13. A metric that disagrees
    with hand arithmetic on the boundary is a metric nobody can check.
    """
    if estimated_minutes <= 0:
        return None
    value = Decimal(actual_minutes) / Decimal(estimated_minutes)
    return float(value.quantize(_PLACES, rounding=ROUND_HALF_UP))


def seoul_date(moment: datetime) -> date:
    """The Seoul calendar day a timestamp falls on.

    SQLite hands back naive datetimes for columns PostgreSQL returns aware, and
    a naive value here would be read as local time on whatever machine is
    running. Stored timestamps are UTC, so that is what a naive one is told it
    is.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo("UTC"))
    return moment.astimezone(SEOUL).date()


def daily_series(plan_id: str, days: list[date] | None = None) -> list[dict]:
    """One row per Seoul day: planned minutes, actual minutes, and the ratio.

    Reads tasks and executions in one pass each rather than a query per day, so
    every day in a comparison sees the same snapshot of the data.
    """
    tasks = db.session.execute(
        select(Task.id, Task.due_date, Task.estimated_minutes).where(
            Task.plan_id == plan_id, Task.deleted_at.is_(None)
        )
    ).all()

    planned: dict[date, int] = {}
    for _task_id, due_date, estimated in tasks:
        planned[due_date] = planned.get(due_date, 0) + estimated

    logs = db.session.execute(
        select(ExecutionLog.started_at, ExecutionLog.actual_minutes)
        .join(Task, Task.id == ExecutionLog.task_id)
        .where(Task.plan_id == plan_id, Task.deleted_at.is_(None))
    ).all()

    actual: dict[date, int] = {}
    counted: dict[date, int] = {}
    for started_at, minutes in logs:
        day = seoul_date(started_at)
        actual[day] = actual.get(day, 0) + minutes
        counted[day] = counted.get(day, 0) + 1

    wanted = days if days is not None else sorted(set(planned) | set(actual))
    return [
        {
            "date": day.isoformat(),
            "estimatedMinutes": planned.get(day, 0),
            "actualMinutes": actual.get(day, 0),
            "executionCount": counted.get(day, 0),
            "ratio": ratio(planned.get(day, 0), actual.get(day, 0)),
        }
        for day in wanted
    ]


def summarize(rows: list[dict]) -> dict:
    """Roll a set of days up with the same formula the days themselves use.

    Summing the minutes and dividing once -- rather than averaging the daily
    ratios -- is what keeps C15 true of the comparison as well as of the days:
    one calculation rule, applied at both levels. Averaging ratios would give a
    different number and would weight a ten-minute day like a six-hour one.
    """
    estimated = sum(row["estimatedMinutes"] for row in rows)
    actual = sum(row["actualMinutes"] for row in rows)
    return {
        "dayCount": len(rows),
        # Days with no planned minutes carry no ratio, so say how many were
        # skipped rather than letting them vanish into the total.
        "daysWithoutRatio": sum(1 for row in rows if row["ratio"] is None),
        "estimatedMinutes": estimated,
        "actualMinutes": actual,
        "ratio": ratio(estimated, actual),
    }


def descriptor() -> dict:
    """What the metric is, sent with every comparison.

    The API says the metric's name, unit, formula and rounding alongside the
    numbers, so that the before and after halves are visibly the same thing
    rather than two numbers a reader has to take on trust (C13-C15).
    """
    return {
        "key": METRIC_KEY,
        "name": METRIC_NAME,
        "unit": METRIC_UNIT,
        "formula": METRIC_FORMULA,
        "rounding": METRIC_ROUNDING,
        "timezone": METRIC_TIMEZONE,
    }
