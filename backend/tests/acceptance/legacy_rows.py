"""Write rows the way the pre-T07 app wrote them, for the migration tests.

Those tests used to seed through the HTTP API while the database sat at an older
revision. That worked as long as every migration only added tables: the current
models still matched the older schema. T07 adds `plans.user_id`, so the models
are now ahead of any revision before it and the insert fails on a column the
database does not have yet.

Seeding with explicit SQL restores the thing the tests are actually for -- rows
that predate a migration survive it -- and is closer to the real upgrade than the
old approach was. The rows on the deployed instance were written by code that had
never heard of `user_id`, which is exactly what these statements are.
"""
from __future__ import annotations

from sqlalchemy import text

from app.extensions import db

# The last revision at which a plan may have no owner. Everything after it is
# the deploy that runs claim_t06_data first, so a test holding pre-claim rows
# upgrades to here and no further -- the NOT NULL migration would, correctly,
# refuse to apply over them.
PRE_CLAIM_REVISION = "a1c7d9e40b52"

# Fixed so the assertions can name them. Synthetic, like every fixture here.
LEGACY_PLAN_ID = "00000000-0000-4000-8000-000000000a01"
LEGACY_TASK_ID = "00000000-0000-4000-8000-000000000b01"

LEGACY_PLAN = {
    "id": LEGACY_PLAN_ID,
    "title": "이관 전 합성 계획",
    "start_date": "2026-09-01",
    "end_date": "2026-09-07",
    "priority": "high",
    "success_criterion": "이관 뒤에도 남아 있을 것",
    "estimated_minutes": 300,
    "carried_improvement": None,
    "created_at": "2026-09-01 09:00:00+00:00",
    "updated_at": "2026-09-01 09:00:00+00:00",
}

LEGACY_TASK = {
    "id": LEGACY_TASK_ID,
    "plan_id": LEGACY_PLAN_ID,
    "content": "이관 전 합성 할 일",
    "status": "active",
    "due_date": "2026-09-03",
    "priority": "high",
    "estimated_minutes": 90,
    "completed_at": None,
    "deleted_at": None,
    "created_at": "2026-09-01 09:05:00+00:00",
    "updated_at": "2026-09-01 09:05:00+00:00",
}


def _insert(table: str, row: dict) -> None:
    columns = ", ".join(row)
    values = ", ".join(f":{name}" for name in row)
    db.session.execute(text(f"INSERT INTO {table} ({columns}) VALUES ({values})"), row)


def seed_legacy_plan_and_task() -> tuple[dict, dict]:
    """Insert one plan and one task using only pre-T07 columns.

    Must be called inside an app context, with the database at the revision the
    test is starting from.
    """
    _insert("plans", LEGACY_PLAN)
    _insert("tasks", LEGACY_TASK)
    db.session.commit()
    return LEGACY_PLAN, LEGACY_TASK
