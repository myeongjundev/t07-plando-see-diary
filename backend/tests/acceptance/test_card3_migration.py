from pathlib import Path

from flask_migrate import upgrade

from app import create_app
from app.extensions import db
from legacy_rows import LEGACY_PLAN, LEGACY_TASK, seed_legacy_plan_and_task
from test_card3_executions import KEY, LOG


def test_card3_upgrade_preserves_card2_data_and_is_repeatable(tmp_path):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"})
    migrations = str(Path(__file__).resolve().parents[2] / "migrations")
    try:
        with app.app_context():
            upgrade(directory=migrations, revision="7f02f5379407")
            # Written with the columns that revision has, so the rows genuinely
            # predate everything the later migrations add.
            seed_legacy_plan_and_task()
            upgrade(directory=migrations)
            upgrade(directory=migrations)
        client = app.test_client()

        plan = client.get(f"/api/plans/{LEGACY_PLAN['id']}").json["plan"]
        assert plan["title"] == LEGACY_PLAN["title"]
        assert plan["startDate"] == LEGACY_PLAN["start_date"]
        assert plan["endDate"] == LEGACY_PLAN["end_date"]
        assert plan["estimatedMinutes"] == LEGACY_PLAN["estimated_minutes"]
        assert plan["successCriterion"] == LEGACY_PLAN["success_criterion"]

        task = client.get(f"/api/tasks/{LEGACY_TASK['id']}").json["task"]
        assert task["content"] == LEGACY_TASK["content"]
        assert task["estimatedMinutes"] == LEGACY_TASK["estimated_minutes"]
        assert task["status"] == LEGACY_TASK["status"]

        assert client.post(f"/api/tasks/{LEGACY_TASK['id']}/executions", json=LOG).status_code == 201
        first = client.post(f"/api/tasks/{LEGACY_TASK['id']}/complete", json=KEY)
        second = client.post(f"/api/tasks/{LEGACY_TASK['id']}/complete", json=KEY)
        assert first.status_code == second.status_code == 200
        assert first.json["completionEvent"] == second.json["completionEvent"]
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
