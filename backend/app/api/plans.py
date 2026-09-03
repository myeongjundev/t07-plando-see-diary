from flask import jsonify, request
from sqlalchemy import text

from app.api import api
from app.auth.csrf import check_state_changing_request
from app.auth.guards import login_required
from app.extensions import db
from app.models import Plan
from app.services.ownership import owned_plan, plans_for
from app.services.plans import ValidationError, create_plan, serialize_plan, serialize_revision, update_plan


def error_response(message: str, *, details: dict[str, str] | None = None, status: int = 400):
    return jsonify({"error": {"message": message, "details": details or {}}}), status


def guard_state_change():
    """CSRF for the endpoints that change something. Returns a response or None."""
    refusal = check_state_changing_request()
    return error_response(refusal[0], status=refusal[1]) if refusal else None


PLAN_NOT_FOUND = "계획을 찾을 수 없습니다."


@api.get("/live")
def live():
    # Hosting probes must not keep a serverless database awake.
    # /health remains the explicit database readiness check.
    return jsonify({"status": "ok"})


@api.get("/health")
def health():
    db.session.execute(text("SELECT 1"))
    engine = db.engine.url.get_backend_name()
    return jsonify({"status": "ok", "database": engine})


@api.get("/plans")
@login_required
def list_plans():
    # Scoped in the query. A list takes no id, so there is nothing a per-row
    # check could be applied to afterwards (T07-C125).
    plans = db.session.scalars(plans_for().order_by(Plan.created_at, Plan.id))
    return jsonify({"plans": [serialize_plan(plan) for plan in plans]})


@api.post("/plans")
@login_required
def post_plan():
    refusal = guard_state_change()
    if refusal:
        return refusal
    try:
        plan = create_plan(request.get_json(silent=True))
    except ValidationError as exc:
        return error_response("계획을 저장할 수 없습니다.", details=exc.errors)
    return jsonify({"plan": serialize_plan(plan)}), 201


@api.get("/plans/<plan_id>")
@login_required
def get_plan(plan_id: str):
    plan = owned_plan(plan_id)
    if plan is None:
        return error_response(PLAN_NOT_FOUND, status=404)
    return jsonify({"plan": serialize_plan(plan)})


@api.patch("/plans/<plan_id>")
@login_required
def patch_plan(plan_id: str):
    refusal = guard_state_change()
    if refusal:
        return refusal
    plan = owned_plan(plan_id)
    if plan is None:
        return error_response(PLAN_NOT_FOUND, status=404)
    try:
        plan = update_plan(plan, request.get_json(silent=True))
    except ValidationError as exc:
        return error_response("계획을 고칠 수 없습니다.", details=exc.errors)
    return jsonify({"plan": serialize_plan(plan)})


@api.get("/plans/<plan_id>/revisions")
@login_required
def get_plan_revisions(plan_id: str):
    plan = owned_plan(plan_id)
    if plan is None:
        return error_response(PLAN_NOT_FOUND, status=404)
    return jsonify({"revisions": [serialize_revision(item) for item in plan.revisions]})

