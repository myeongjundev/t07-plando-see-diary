"""Recording and reading a plan's rule change. T07-C09 to C15.

Scoped like everything else: the plan is looked up through `owned_plan`, so a
rule change on somebody else's study is a 404 and not a 403 (T07-C121).
"""
from flask import jsonify, request
from sqlalchemy import select

from app.api import api
from app.api.plans import PLAN_NOT_FOUND, error_response, guard_state_change
from app.auth.guards import login_required
from app.extensions import db
from app.models import PlanRuleChange
from app.services import metrics
from app.services.ownership import owned_plan
from app.services.plans import ValidationError
from app.services.rule_changes import (
    comparison,
    create_rule_change,
    day_number,
    serialize_rule_change,
    study_days,
)


@api.get("/plans/<plan_id>/rule-changes")
@login_required
def list_rule_changes(plan_id):
    plan = owned_plan(plan_id)
    if plan is None:
        return error_response(PLAN_NOT_FOUND, status=404)
    rows = db.session.scalars(
        select(PlanRuleChange)
        .where(PlanRuleChange.plan_id == plan_id)
        .order_by(PlanRuleChange.changed_at, PlanRuleChange.id)
    ).all()
    return jsonify({
        "ruleChanges": [
            {**serialize_rule_change(row), "comparison": comparison(plan, row)} for row in rows
        ],
    })


@api.post("/plans/<plan_id>/rule-changes")
@login_required
def post_rule_change(plan_id):
    refusal = guard_state_change()
    if refusal:
        return refusal
    plan = owned_plan(plan_id)
    if plan is None:
        return error_response(PLAN_NOT_FOUND, status=404)
    try:
        change = create_rule_change(plan, request.get_json(silent=True))
    except ValidationError as exc:
        return error_response("규칙 변경을 기록할 수 없습니다.", details=exc.errors)
    return jsonify({
        "ruleChange": {**serialize_rule_change(change), "comparison": comparison(plan, change)},
    }), 201


@api.get("/plans/<plan_id>/study")
@login_required
def plan_study(plan_id):
    """The day-by-day view the rule-change screen is built on.

    One request rather than three, because the screen needs the same snapshot
    for all of it: which study day each execution belongs to (so day 1 and day 2
    can be offered for citation), the daily metric, and the metric's own
    description. Assembling that from separate calls would let the day numbering
    and the numbers come from different moments.
    """
    plan = owned_plan(plan_id)
    if plan is None:
        return error_response(PLAN_NOT_FOUND, status=404)

    days = study_days(plan)
    series = metrics.daily_series(plan.id, days)
    return jsonify({
        "planId": plan.id,
        "metric": metrics.descriptor(),
        "startDate": plan.start_date.isoformat(),
        "endDate": plan.end_date.isoformat(),
        "days": [
            {"dayNumber": index + 1, **row} for index, row in enumerate(series)
        ],
        "executions": _executions_by_day(plan),
    })


def _executions_by_day(plan):
    """This plan's execution records, each tagged with its study day.

    The day number is computed here rather than in the browser because the
    boundary is a Seoul day and the reviewer's browser may not be in Seoul.
    A record's study day must not depend on who is looking at it.
    """
    from app.models import ExecutionLog, Task
    from app.services.executions import serialize_execution

    rows = db.session.execute(
        select(ExecutionLog, Task.content)
        .join(Task, Task.id == ExecutionLog.task_id)
        .where(Task.plan_id == plan.id, Task.deleted_at.is_(None))
        .order_by(ExecutionLog.started_at, ExecutionLog.id)
    ).all()
    return [
        {
            **serialize_execution(log),
            "taskContent": content,
            "dayNumber": day_number(plan, log.started_at),
        }
        for log, content in rows
    ]
