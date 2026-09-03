from pathlib import Path

from flask_migrate import upgrade
from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import Plan, Task
from conftest import browser_for
from legacy_rows import LEGACY_PLAN, LEGACY_TASK, seed_legacy_plan_and_task
from test_card2_tasks import create_plan, create_task
from test_card3_executions import KEY, LOG


def test_card3_upgrade_preserves_card2_data_and_is_repeatable(tmp_path):
    """Rows written before the migration survive it, and it can run twice.

    The survival half is checked in the database rather than through the API,
    because T07 scopes every endpoint to the requesting account and these rows
    have no owner yet -- they predate accounts, and `claim_t06_data` is what
    will give them one. Unreachable-until-claimed is the correct behaviour, so
    asserting it here is the honest test; asking the API would only prove the
    scoping works, which is a different test's job.
    """
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"})
    migrations = str(Path(__file__).resolve().parents[2] / "migrations")
    try:
        with app.app_context():
            upgrade(directory=migrations, revision="7f02f5379407")
            # Written with the columns that revision has, so the rows genuinely
            # predate everything the later migrations add.
            seed_legacy_plan_and_task()
            upgrade(directory=migrations)
            upgrade(directory=migrations)  # Idempotent.

            plan = db.session.scalar(select(Plan).where(Plan.id == LEGACY_PLAN["id"]))
            assert plan is not None
            assert plan.title == LEGACY_PLAN["title"]
            assert plan.start_date.isoformat() == LEGACY_PLAN["start_date"]
            assert plan.end_date.isoformat() == LEGACY_PLAN["end_date"]
            assert plan.estimated_minutes == LEGACY_PLAN["estimated_minutes"]
            assert plan.success_criterion == LEGACY_PLAN["success_criterion"]
            # Waiting for the claim. Nullable exists for precisely this window.
            assert plan.user_id is None

            task = db.session.scalar(select(Task).where(Task.id == LEGACY_TASK["id"]))
            assert task is not None
            assert task.content == LEGACY_TASK["content"]
            assert task.estimated_minutes == LEGACY_TASK["estimated_minutes"]
            assert task.status == LEGACY_TASK["status"]

        # And the application still works on the far side of the migration.
        client = browser_for(app)
        owned_plan = create_plan(client)
        owned_task = create_task(client, owned_plan["id"])
        url = f"/api/tasks/{owned_task['id']}"
        assert client.post(url + "/executions", json=LOG).status_code == 201
        first = client.post(url + "/complete", json=KEY)
        second = client.post(url + "/complete", json=KEY)
        assert first.status_code == second.status_code == 200
        assert first.json["completionEvent"] == second.json["completionEvent"]
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
