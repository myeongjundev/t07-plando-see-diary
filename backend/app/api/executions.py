from flask import jsonify, request
from sqlalchemy import select

from app.api import api
from app.api.plans import error_response, guard_state_change
from app.api.tasks import TASK_NOT_FOUND, active_task
from app.auth.guards import login_required
from app.extensions import db
from app.models import CompletionEvent, ExecutionLog
from app.services.executions import create_execution, serialize_completion, serialize_execution
from app.services.plans import ValidationError


@api.get("/tasks/<task_id>/executions")
@login_required
def list_executions(task_id):
    if active_task(task_id) is None:
        return error_response(TASK_NOT_FOUND, status=404)
    logs = db.session.scalars(select(ExecutionLog).where(ExecutionLog.task_id == task_id)
                              .order_by(ExecutionLog.started_at, ExecutionLog.id))
    return jsonify({"executions": [serialize_execution(log) for log in logs]})


@api.post("/tasks/<task_id>/executions")
@login_required
def post_execution(task_id):
    refusal = guard_state_change()
    if refusal:
        return refusal
    task = active_task(task_id)
    if task is None:
        return error_response(TASK_NOT_FOUND, status=404)
    try:
        log = create_execution(task, request.get_json(silent=True))
    except ValidationError as exc:
        return error_response("실행 기록을 저장할 수 없습니다.", details=exc.errors)
    return jsonify({"execution": serialize_execution(log)}), 201


@api.get("/tasks/<task_id>/completions")
@login_required
def list_completions(task_id):
    if active_task(task_id) is None:
        return error_response(TASK_NOT_FOUND, status=404)
    events = db.session.scalars(select(CompletionEvent).where(CompletionEvent.task_id == task_id)
                                .order_by(CompletionEvent.completed_at, CompletionEvent.id))
    return jsonify({"completionEvents": [serialize_completion(event) for event in events]})
