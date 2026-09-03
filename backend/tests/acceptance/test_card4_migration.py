from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier

from flask_migrate import upgrade
from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import ExecutionLog, Plan
from conftest import browser_for, copy_session
from legacy_rows import LEGACY_PLAN, LEGACY_TASK, PRE_CLAIM_REVISION, seed_legacy_plan_and_task
from test_card2_tasks import create_plan
from test_card3_executions import LOG
from test_card4_see import NEXT, REFLECTION


def test_card4_upgrade_preserves_logs_and_concurrent_next_plan_is_single(tmp_path):
    """Execution logs survive the migration, and next-plan stays idempotent.

    As in the card 3 migration test, the pre-migration rows are checked in the
    database: they have no owner until `claim_t06_data` runs, so the scoped API
    correctly cannot see them.
    """
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'card4.db').as_posix()}"})
    migrations = str(Path(__file__).resolve().parents[2] / "migrations")
    try:
        with app.app_context():
            upgrade(directory=migrations, revision="fb630bb3ebd6")
            seed_legacy_plan_and_task()
            # Execution logs exist at this revision, so one can be written the
            # way the old app wrote it and then carried across.
            db.session.add(ExecutionLog(
                task_id=LEGACY_TASK["id"],
                started_at=datetime.fromisoformat(LOG["startedAt"]),
                ended_at=datetime.fromisoformat(LOG["endedAt"]),
                actual_minutes=LOG["actualMinutes"],
                blocker_reason=LOG["blockerReason"],
            ))
            db.session.commit()
            log_id = db.session.scalar(select(ExecutionLog.id))

            # Stops before the NOT NULL migration: these rows have no owner yet,
            # and that migration refuses to apply over them by design.
            upgrade(directory=migrations, revision=PRE_CLAIM_REVISION)
            upgrade(directory=migrations, revision=PRE_CLAIM_REVISION)  # Idempotent.

            carried = db.session.get(ExecutionLog, log_id)
            assert carried is not None
            assert carried.actual_minutes == LOG["actualMinutes"]
            assert carried.task_id == LEGACY_TASK["id"]
            assert db.session.scalar(select(Plan).where(Plan.id == LEGACY_PLAN["id"])).user_id is None

        client = browser_for(app)
        plan = create_plan(client)
        row = client.post(f"/api/plans/{plan['id']}/reflections", json=REFLECTION).json["reflection"]
        barrier = Barrier(4)

        def create(_):
            with app.test_client() as worker:
                copy_session(client, worker)
                barrier.wait(timeout=10)
                return worker.post(f"/api/reflections/{row['id']}/next-plan", json=NEXT)

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(create, range(4)))
        assert sorted(result.status_code for result in results) == [200, 200, 200, 201]
        assert len({result.json["plan"]["id"] for result in results}) == 1
        # The account's own two plans. The unclaimed legacy plan is not theirs.
        assert len(client.get("/api/plans").json["plans"]) == 2
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
