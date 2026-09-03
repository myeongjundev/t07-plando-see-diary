from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.services.ownership import owner_for_new_plan
from app.models import Plan, PlanRevision
from app.time import utc_iso

PRIORITIES = {"high", "medium", "low"}
EDITABLE_FIELDS = {
    "title",
    "startDate",
    "endDate",
    "priority",
    "successCriterion",
    "estimatedMinutes",
    "carriedImprovement",
}


class ValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("Invalid plan")
        self.errors = errors


def _text(payload: dict[str, Any], key: str, *, max_length: int, required: bool = True) -> str | None:
    value = payload.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValidationError({key: "공백이 아닌 글자를 입력하세요."})
    cleaned = value.strip()
    if len(cleaned) > max_length:
        raise ValidationError({key: f"{max_length}자 이하여야 합니다."})
    return cleaned


def _date(payload: dict[str, Any], key: str) -> date:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValidationError({key: "YYYY-MM-DD 형식의 날짜를 입력하세요."})
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({key: "YYYY-MM-DD 형식의 날짜를 입력하세요."}) from exc


def validate_plan(payload: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationError({"body": "JSON 객체가 필요합니다."})
    unknown = set(payload) - EDITABLE_FIELDS
    if unknown:
        raise ValidationError({"body": f"알 수 없는 항목: {', '.join(sorted(unknown))}"})

    values: dict[str, Any] = {}
    required_keys = EDITABLE_FIELDS - {"carriedImprovement"}
    if partial and not payload:
        raise ValidationError({"body": "고칠 항목을 하나 이상 보내세요."})
    if not partial:
        missing = required_keys - set(payload)
        if missing:
            raise ValidationError({"body": f"필수 항목 누락: {', '.join(sorted(missing))}"})

    if "title" in payload:
        values["title"] = _text(payload, "title", max_length=160)
    if "successCriterion" in payload:
        values["success_criterion"] = _text(payload, "successCriterion", max_length=500)
    if "carriedImprovement" in payload:
        raw = payload.get("carriedImprovement")
        values["carried_improvement"] = None if raw in (None, "") else _text(payload, "carriedImprovement", max_length=500)
    if "startDate" in payload:
        values["start_date"] = _date(payload, "startDate")
    if "endDate" in payload:
        values["end_date"] = _date(payload, "endDate")
    if "priority" in payload:
        priority = payload.get("priority")
        if not isinstance(priority, str) or priority not in PRIORITIES:
            raise ValidationError({"priority": "high, medium, low 중 하나여야 합니다."})
        values["priority"] = priority
    if "estimatedMinutes" in payload:
        minutes = payload.get("estimatedMinutes")
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not 0 <= minutes <= 1_000_000:
            raise ValidationError({"estimatedMinutes": "0 이상의 정수 분이어야 합니다."})
        values["estimated_minutes"] = minutes

    start = values.get("start_date")
    end = values.get("end_date")
    if start and end and end < start:
        raise ValidationError({"endDate": "종료일은 시작일보다 빠를 수 없습니다."})
    return values


def create_plan(payload: dict[str, Any]) -> Plan:
    values = validate_plan(payload)
    # Stamped here rather than left to the caller. A plan created without an
    # owner belongs to nobody: it is invisible to every scoped query, which
    # reads as the row having been lost rather than as the bug it is.
    plan = Plan(user_id=owner_for_new_plan(), **values)
    db.session.add(plan)
    db.session.commit()
    return plan


def update_plan(plan: Plan, payload: dict[str, Any]) -> Plan:
    values = validate_plan(payload, partial=True)
    candidate_start = values.get("start_date", plan.start_date)
    candidate_end = values.get("end_date", plan.end_date)
    if candidate_end < candidate_start:
        raise ValidationError({"endDate": "종료일은 시작일보다 빠를 수 없습니다."})

    revision_number = db.session.scalar(
        select(func.count(PlanRevision.revision_id)).where(PlanRevision.plan_id == plan.id)
    ) + 1
    revision = PlanRevision(
        plan_id=plan.id,
        revision_number=revision_number,
        title=plan.title,
        start_date=plan.start_date,
        end_date=plan.end_date,
        priority=plan.priority,
        success_criterion=plan.success_criterion,
        estimated_minutes=plan.estimated_minutes,
        carried_improvement=plan.carried_improvement,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )
    db.session.add(revision)
    for key, value in values.items():
        setattr(plan, key, value)
    db.session.commit()
    return plan


def serialize_plan(plan: Plan) -> dict[str, Any]:
    return {
        "id": plan.id,
        "title": plan.title,
        "startDate": plan.start_date.isoformat(),
        "endDate": plan.end_date.isoformat(),
        "priority": plan.priority,
        "successCriterion": plan.success_criterion,
        "estimatedMinutes": plan.estimated_minutes,
        "durationUnit": "minutes",
        "carriedImprovement": plan.carried_improvement,
        "createdAt": utc_iso(plan.created_at),
        "updatedAt": utc_iso(plan.updated_at),
    }


def serialize_revision(revision: PlanRevision) -> dict[str, Any]:
    return {
        "id": revision.plan_id,
        "revisionId": revision.revision_id,
        "planId": revision.plan_id,
        "revisionNumber": revision.revision_number,
        "title": revision.title,
        "startDate": revision.start_date.isoformat(),
        "endDate": revision.end_date.isoformat(),
        "priority": revision.priority,
        "successCriterion": revision.success_criterion,
        "estimatedMinutes": revision.estimated_minutes,
        "durationUnit": "minutes",
        "carriedImprovement": revision.carried_improvement,
        "createdAt": utc_iso(revision.created_at),
        "updatedAt": utc_iso(revision.updated_at),
        "replacedAt": utc_iso(revision.replaced_at),
    }
