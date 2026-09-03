from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import ExecutionLog, Plan, Reflection, Task
from app.models.plan import utc_now
from app.services.executions import serialize_execution, utc_iso
from app.services.plans import ValidationError, validate_plan
from app.services.tasks import serialize_task


def parse_period(start, end, *, required=False):
    if start is None and end is None and not required:
        return None, None
    try:
        if not isinstance(start, str) or not isinstance(end, str):
            raise ValueError
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if first.isoformat() != start or last.isoformat() != end or last < first:
            raise ValueError
    except ValueError as exc:
        raise ValidationError({"period": "시작일과 종료일을 YYYY-MM-DD로 입력하고 날짜 순서를 확인하세요."}) from exc
    return first, last


def aggregate_plan(plan: Plan, start=None, end=None) -> dict:
    first, last = parse_period(start, end)
    now = utc_now()
    today = now.astimezone(ZoneInfo("Asia/Seoul")).date()
    # One joined statement gives all metrics and drill-downs the same row snapshot.
    statement = (select(Task, ExecutionLog).outerjoin(ExecutionLog, ExecutionLog.task_id == Task.id)
                 .options(selectinload(Task.tags))
                 .where(Task.plan_id == plan.id, Task.deleted_at.is_(None))
                 .order_by(Task.due_date, Task.id, ExecutionLog.started_at, ExecutionLog.id))
    if first is not None:
        statement = statement.where(Task.due_date.between(first, last))
    tasks, logs = {}, {}
    for task, log in db.session.execute(statement):
        tasks[task.id] = task
        if log is not None:
            logs[log.id] = log
    completed = sorted(t.id for t in tasks.values() if t.status == "completed")
    overdue = [t.id for t in tasks.values() if t.status != "completed" and t.due_date < today]
    blocker_logs = [log for log in logs.values() if log.blocker_reason.strip()]
    blocked = sorted({log.task_id for log in blocker_logs})
    estimated = sum(task.estimated_minutes for task in tasks.values())
    actual = sum(log.actual_minutes for log in logs.values())

    def source(task_ids, log_ids=()):
        return {"taskIds": list(task_ids), "executionIds": list(log_ids)}

    return {
        "planId": plan.id, "asOf": utc_iso(now), "today": today.isoformat(),
        "timezone": "Asia/Seoul", "durationUnit": "minutes",
        "scope": "dueDate" if first is not None else "plan",
        "periodStart": (first or min([plan.start_date, *(t.due_date for t in tasks.values())])).isoformat(),
        "periodEnd": (last or max([plan.end_date, *(t.due_date for t in tasks.values())])).isoformat(),
        "taskCount": len(tasks), "completedCount": len(completed), "completedTaskIds": completed,
        "overdueCount": len(overdue), "blockedTaskCount": len(blocked),
        "estimatedMinutes": estimated, "actualMinutes": actual, "varianceMinutes": actual - estimated,
        "sources": {
            "taskCount": source(tasks), "completedCount": source(completed),
            "overdueCount": source(overdue),
            "blockedTaskCount": source(blocked, [log.id for log in blocker_logs]),
            "estimatedMinutes": source(tasks),
            "actualMinutes": source(sorted({log.task_id for log in logs.values()}), logs),
            "varianceMinutes": source(tasks, logs),
        },
        "records": {"tasks": [serialize_task(task) for task in tasks.values()],
                    "executions": [serialize_execution(log) for log in logs.values()]},
    }


def create_reflection(plan: Plan, payload) -> Reflection:
    if not isinstance(payload, dict) or set(payload) != {"periodStart", "periodEnd", "improvement"}:
        raise ValidationError({"body": "회고 기간과 개선 문장을 입력하세요."})
    first, last = parse_period(payload["periodStart"], payload["periodEnd"], required=True)
    improvement = payload["improvement"]
    if (not isinstance(improvement, str) or not improvement.strip() or len(improvement) > 500
            or any(char in improvement for char in "\r\n")):
        raise ValidationError({"improvement": "개선할 점을 공백이 아닌 한 줄, 500자 이하로 입력하세요."})
    reflection = Reflection(plan_id=plan.id, period_start=first, period_end=last, improvement=improvement)
    db.session.add(reflection)
    db.session.commit()
    return reflection


def next_plan(reflection: Reflection, payload) -> tuple[Plan, bool]:
    if not isinstance(payload, dict) or "carriedImprovement" in payload:
        raise ValidationError({"body": "다음 계획을 입력하세요. 개선 문장은 저장된 회고에서 전달됩니다."})
    values = validate_plan({**payload, "carriedImprovement": None})
    # Serializes retries, including requests from different tabs/connections.
    db.session.execute(update(Reflection).where(Reflection.id == reflection.id)
                       .values(next_plan_id=Reflection.next_plan_id)
                       .execution_options(synchronize_session=False))
    db.session.refresh(reflection)
    if reflection.next_plan_id:
        plan = db.session.get(Plan, reflection.next_plan_id)
        db.session.commit()
        return plan, True
    values["carried_improvement"] = reflection.improvement
    # The successor belongs to whoever owns the plan the reflection is on, not
    # to whoever happens to be asking. The reflection was already checked as
    # theirs, so these are the same user -- taking it from the row rather than
    # the request keeps that true even if the guard above ever moves.
    parent = db.session.get(Plan, reflection.plan_id)
    plan = Plan(user_id=parent.user_id, **values)
    db.session.add(plan)
    db.session.flush()
    reflection.next_plan_id = plan.id
    db.session.commit()
    return plan, False


def serialize_reflection(reflection: Reflection):
    return {"id": reflection.id, "planId": reflection.plan_id,
            "periodStart": reflection.period_start.isoformat(), "periodEnd": reflection.period_end.isoformat(),
            "improvement": reflection.improvement, "nextPlanId": reflection.next_plan_id,
            "createdAt": utc_iso(reflection.created_at)}
