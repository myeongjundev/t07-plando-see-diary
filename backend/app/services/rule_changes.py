"""Recording a mid-study change to the plan's own rule. T07-C09 to C15.

The criteria are about ordering and about pointing at the right records, so this
module is mostly refusals. Everything it checks, it checks in one transaction
against rows it has just read, because each of these is a claim about the state
of the data and not about the shape of the request:

  C12  the two citations are executions on *this* plan, one on the study's day
       one and one on its day two, in that order
  C09  `changed_at` is after the day-2 record and before any day-3 record
  C10  the time is recorded; C11 the reason is

The before/after comparison is not computed here. It comes from
`app.services.metrics`, which is the only module that knows the formula, so that
C13-C15 are true because there is one implementation rather than because two
were written carefully.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import ExecutionLog, Plan, PlanRuleChange, PlanRuleChangeCitation, Task
from app.services import metrics
from app.services.plans import ValidationError
from app.time import utc_iso
from app.models.plan import utc_now

MAX_REASON_CHARS = 500
MAX_RULE_CHARS = 500

FIELDS = {"reason", "ruleBefore", "ruleAfter", "day1ExecutionId", "day2ExecutionId"}


def _text(payload: dict, key: str, limit: int, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValidationError({key: f"{label}을(를) 공백이 아닌 {limit}자 이하로 입력하세요."})
    return value.strip()


def _execution_on_plan(plan_id: str, execution_id) -> ExecutionLog:
    """One execution record, or a refusal naming which citation is wrong.

    Joined through `tasks` to the plan rather than looked up by id and checked
    afterwards. An id belonging to another plan -- another account's, even --
    simply does not come back, so there is no window in which the wrong row has
    been loaded and is waiting to be rejected.
    """
    if not isinstance(execution_id, str) or not execution_id:
        raise ValidationError({"citations": "1일차와 2일차 기록을 각각 하나씩 고르세요."})
    row = db.session.scalar(
        select(ExecutionLog)
        .join(Task, Task.id == ExecutionLog.task_id)
        .where(
            ExecutionLog.id == execution_id,
            Task.plan_id == plan_id,
            Task.deleted_at.is_(None),
        )
    )
    if row is None:
        raise ValidationError({"citations": "이 계획의 실행 기록만 인용할 수 있습니다."})
    return row


def study_days(plan: Plan) -> list[date]:
    """The plan's days, in Seoul, from its start date.

    Day numbering is the plan's own: day 1 is `start_date`. Deriving it from
    "the first day that happens to have a record" would renumber the whole study
    the moment a day was left empty, and C09's "day 2" and "day 3" would mean
    different days on different readings.
    """
    span = (plan.end_date - plan.start_date).days
    return [plan.start_date + timedelta(days=offset) for offset in range(span + 1)]


def day_number(plan: Plan, moment: datetime) -> int:
    """Which study day a timestamp falls on. 1-based; can run past the plan's end."""
    return (metrics.seoul_date(moment) - plan.start_date).days + 1


def create_rule_change(plan: Plan, payload) -> PlanRuleChange:
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        raise ValidationError({"body": "변경 이유와 규칙 전후, 1·2일차 기록을 입력하세요."})

    reason = _text(payload, "reason", MAX_REASON_CHARS, "변경 이유")
    rule_before = _text(payload, "ruleBefore", MAX_RULE_CHARS, "바꾸기 전 규칙")
    rule_after = _text(payload, "ruleAfter", MAX_RULE_CHARS, "바꾼 뒤 규칙")
    if rule_before == rule_after:
        raise ValidationError({"ruleAfter": "바꾸기 전과 바꾼 뒤가 같으면 규칙 변경이 아닙니다."})

    first = _execution_on_plan(plan.id, payload["day1ExecutionId"])
    second = _execution_on_plan(plan.id, payload["day2ExecutionId"])
    if first.id == second.id:
        raise ValidationError({"citations": "1일차와 2일차로 같은 기록을 고를 수 없습니다."})

    # C12: not "two records" but the day-1 and day-2 records. The check is on
    # the Seoul day each was started, against the plan's own day numbering.
    if day_number(plan, first.started_at) != 1:
        raise ValidationError({"day1ExecutionId": "1일차에 시작한 기록이 아닙니다."})
    if day_number(plan, second.started_at) != 2:
        raise ValidationError({"day2ExecutionId": "2일차에 시작한 기록이 아닙니다."})

    changed_at = utc_now()

    # C09, first half: after the day-2 record. Compared against when that record
    # finished, not when it started -- a change made while day 2 was still being
    # worked cannot have been prompted by it.
    if changed_at <= _aware(second.ended_at):
        raise ValidationError({"changedAt": "2일차 기록이 끝난 뒤에 규칙을 바꿀 수 있습니다."})

    # C09, second half: before the day-3 record. Enforced by refusing to accept
    # the change late rather than by editing history -- if a day-3 record
    # already exists, the ordering the criterion asks for cannot be produced,
    # and saying so now is the only honest answer.
    if _day_three_record(plan) is not None:
        raise ValidationError(
            {"changedAt": "3일차 기록이 이미 있어 이 순서로 기록할 수 없습니다."}
        )

    change = PlanRuleChange(
        plan_id=plan.id,
        changed_at=changed_at,
        reason=reason,
        rule_before=rule_before,
        rule_after=rule_after,
    )
    change.citations = [
        PlanRuleChangeCitation(day_number=1, execution_id=first.id),
        PlanRuleChangeCitation(day_number=2, execution_id=second.id),
    ]
    db.session.add(change)
    db.session.commit()
    return change


def _aware(moment: datetime) -> datetime:
    """SQLite returns naive datetimes for columns PostgreSQL returns aware."""
    from datetime import timezone

    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _day_three_record(plan: Plan) -> ExecutionLog | None:
    """The earliest execution on or after study day 3, if there is one."""
    rows = db.session.scalars(
        select(ExecutionLog)
        .join(Task, Task.id == ExecutionLog.task_id)
        .where(Task.plan_id == plan.id, Task.deleted_at.is_(None))
        .order_by(ExecutionLog.started_at)
    )
    for row in rows:
        if day_number(plan, row.started_at) >= 3:
            return row
    return None


def observation_plan_id() -> str | None:
    """The one plan the five-day study is about, if this deployment has one.

    Fixed in `docs/T07-STUDY-PROTOCOL.md` and set in the environment, so the
    ordering rule below applies to that plan and nothing else. Every other plan
    -- including the T06 rows the claim brought across -- is an ordinary diary
    the user may write in whatever order they like.
    """
    return os.getenv("OBSERVATION_PLAN_ID") or None


def blocks_execution(plan: Plan, started_at: datetime) -> bool:
    """Whether a new execution would land on day 3+ with no rule change recorded.

    Called from the execution-creation path for the observation plan only. The
    design asks for the order to be checked on both sides, and this is the other
    side: without it, the whole five-day study can be invalidated by logging
    day 3 before writing down the change, at which point the only remedies are
    editing timestamps or starting the five days again.
    """
    if day_number(plan, started_at) < 3:
        return False
    return db.session.scalar(
        select(PlanRuleChange.id).where(PlanRuleChange.plan_id == plan.id).limit(1)
    ) is None


def comparison(plan: Plan, change: PlanRuleChange) -> dict:
    """The days before the change and the days after, in the same metric.

    The split follows the citations, not the change's own timestamp. C09 puts
    the change *on* day 2 -- after that evening's record, before the next
    morning's -- so splitting by the day it happened would put day 2 in the
    'after' half, and the comparison would be one day against four rather than
    the before and after the criteria are about. The cited days are the before;
    everything from the next day is the after.

    Both halves go through `metrics.summarize`, and the metric descriptor rides
    along, so C13-C15 can be read off the response rather than inferred from two
    numbers that a reader has to trust were computed the same way.
    """
    boundary = max(citation.day_number for citation in change.citations) + 1
    days = study_days(plan)
    before = [day for day in days if (day - plan.start_date).days + 1 < boundary]
    after = [day for day in days if (day - plan.start_date).days + 1 >= boundary]
    series = {row["date"]: row for row in metrics.daily_series(plan.id, days)}
    return {
        "metric": metrics.descriptor(),
        "before": {
            **metrics.summarize([series[day.isoformat()] for day in before]),
            "days": [series[day.isoformat()] for day in before],
        },
        "after": {
            **metrics.summarize([series[day.isoformat()] for day in after]),
            "days": [series[day.isoformat()] for day in after],
        },
    }


def serialize_rule_change(change: PlanRuleChange) -> dict:
    return {
        "id": change.id,
        "planId": change.plan_id,
        "changedAt": utc_iso(_aware(change.changed_at)),
        "reason": change.reason,
        "ruleBefore": change.rule_before,
        "ruleAfter": change.rule_after,
        "citedExecutionIds": {
            f"day{citation.day_number}": citation.execution_id
            for citation in sorted(change.citations, key=lambda row: row.day_number)
        },
        "createdAt": utc_iso(_aware(change.created_at)),
    }
