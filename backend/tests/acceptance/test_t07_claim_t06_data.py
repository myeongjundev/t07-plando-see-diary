"""Attaching the T06 rows to an account. T07-C100.

This is the one script that edits real diary data on the deployed database, and
it runs once, unattended, during a boot nobody is watching. So the tests are
mostly about what it refuses to do.

They run against migration a1c7d9e40b52 rather than head, because that is the
only schema the claim ever sees. At head `plans.user_id` is NOT NULL and an
unowned plan cannot exist -- which is the point of step 10, and would make the
state these tests are about unrepresentable.
"""
from __future__ import annotations

import importlib.util
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text

from app import create_app
from app.extensions import db
from app.models import Plan, Task, User
from flask_migrate import upgrade
from legacy_rows import LEGACY_PLAN, LEGACY_TASK, seed_legacy_plan_and_task

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "claim_t06_data.py"
MIGRATIONS = str(Path(__file__).resolve().parents[2] / "migrations")
# The revision the claim runs against: user_id exists and is still nullable.
CLAIM_REVISION = "a1c7d9e40b52"

_spec = importlib.util.spec_from_file_location("claim_t06_data", SCRIPT)
claim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(claim)

EMAIL = "owner@example.invalid"
PASSWORD = "합성-이관-비밀번호-6b2e"
OTHER_PLAN_ID = "00000000-0000-4000-8000-000000000a02"
DELETED_TASK_ID = "00000000-0000-4000-8000-000000000b02"


@pytest.fixture()
def legacy(tmp_path):
    """A pre-claim database: two unowned plans and one soft-deleted task.

    One plan to keep, one standing for the leftover demo rows, and a task that
    T06 had already deleted -- the shape the deployed database is actually in.
    """
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'claim.db').as_posix()}",
    })
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision=CLAIM_REVISION)
        seed_legacy_plan_and_task()
        db.session.execute(text(
            "INSERT INTO plans (id, title, start_date, end_date, priority,"
            " success_criterion, estimated_minutes, created_at, updated_at)"
            " VALUES (:id, :title, :start, :end, 'low', '합성', 10, :now, :now)"
        ), {"id": OTHER_PLAN_ID, "title": "합성 데모 계획", "start": LEGACY_PLAN["start_date"],
            "end": LEGACY_PLAN["end_date"], "now": LEGACY_PLAN["created_at"]})
        db.session.add(Task(
            id=DELETED_TASK_ID, plan_id=LEGACY_PLAN["id"], content="<script>합성</script>",
            status="active", due_date=date.fromisoformat(LEGACY_TASK["due_date"]),
            priority="low", estimated_minutes=5, deleted_at=datetime.now(timezone.utc),
        ))
        db.session.commit()
        try:
            yield app, LEGACY_PLAN["id"], OTHER_PLAN_ID
        finally:
            db.session.remove()
            db.engine.dispose()


def test_c100_claim_leaves_no_orphan_plan(legacy):
    _app, keep, drop = legacy
    report = claim.run(EMAIL, PASSWORD, [keep], [drop], [DELETED_TASK_ID], apply=True)

    assert report["unowned_after"] == 0
    owner = db.session.scalar(select(User).where(User.email == EMAIL))
    assert owner is not None
    assert db.session.get(Plan, keep).user_id == owner.id
    assert db.session.get(Plan, drop) is None
    # The live task came across; the soft-deleted synthetic one did not.
    assert db.session.get(Task, LEGACY_TASK["id"]) is not None
    assert db.session.get(Task, DELETED_TASK_ID) is None


def test_a_plan_in_neither_list_stops_the_run(legacy):
    """The lists exist because a person decided. An unlisted plan means nobody
    did, and guessing at it is how real data gets deleted."""
    _app, keep, _drop = legacy
    with pytest.raises(claim.ClaimRefused, match=OTHER_PLAN_ID):
        claim.run(EMAIL, PASSWORD, [keep], [], apply=True)
    assert db.session.get(Plan, keep).user_id is None
    assert db.session.scalar(select(db.func.count()).select_from(User)) == 0


def test_an_id_in_both_lists_stops_the_run(legacy):
    _app, keep, drop = legacy
    with pytest.raises(claim.ClaimRefused, match="both lists"):
        claim.run(EMAIL, PASSWORD, [keep, drop], [drop], apply=True)
    assert db.session.get(Plan, keep).user_id is None


def test_an_active_task_is_never_deleted(legacy):
    """A mistyped task id must not be able to remove live diary work."""
    _app, keep, drop = legacy
    with pytest.raises(claim.ClaimRefused, match="active task"):
        claim.run(EMAIL, PASSWORD, [keep], [drop], [LEGACY_TASK["id"]], apply=True)
    assert db.session.get(Task, LEGACY_TASK["id"]) is not None
    assert db.session.get(Plan, keep).user_id is None


def test_a_task_outside_the_claimed_plans_is_refused(legacy):
    _app, keep, drop = legacy
    stray = "00000000-0000-4000-8000-000000000b03"
    db.session.add(Task(
        id=stray, plan_id=drop, content="합성", status="active",
        due_date=date.fromisoformat(LEGACY_TASK["due_date"]), priority="low",
        estimated_minutes=5, deleted_at=datetime.now(timezone.utc),
    ))
    db.session.commit()
    with pytest.raises(claim.ClaimRefused, match="selected for claim"):
        claim.run(EMAIL, PASSWORD, [keep], [drop], [stray], apply=True)


def test_without_apply_nothing_changes(legacy):
    """A deploy that runs this by accident must be a no-op."""
    _app, keep, drop = legacy
    report = claim.run(EMAIL, PASSWORD, [keep], [drop], [DELETED_TASK_ID], apply=False)

    assert report["to_claim"] == 1 and report["to_delete"] == 1
    assert report["to_delete_tasks"] == 1
    assert report["unowned_after"] == 2
    assert db.session.get(Plan, keep).user_id is None
    assert db.session.get(Plan, drop) is not None
    assert db.session.get(Task, DELETED_TASK_ID) is not None
    assert db.session.scalar(select(db.func.count()).select_from(User)) == 0


def test_running_twice_is_the_same_as_running_once(legacy):
    """A deploy can be retried -- by Render, or by someone pushing again."""
    _app, keep, drop = legacy
    first = claim.run(EMAIL, PASSWORD, [keep], [drop], [DELETED_TASK_ID], apply=True)
    second = claim.run(EMAIL, PASSWORD, [keep], [drop], [DELETED_TASK_ID], apply=True)

    assert first["account_created"] is True
    assert second["account_created"] is False
    assert second["to_claim"] == 0 and second["to_delete"] == 0
    assert second["to_delete_tasks"] == 0
    assert second["unowned_after"] == 0
    assert db.session.scalar(select(db.func.count()).select_from(User)) == 1
    assert db.session.scalar(select(db.func.count()).select_from(Plan)) == 1


def test_an_existing_account_is_reused_not_duplicated(legacy):
    _app, keep, drop = legacy
    db.session.add(User(email=EMAIL, password_hash="$argon2id$synthetic"))
    db.session.commit()
    report = claim.run(EMAIL, PASSWORD, [keep], [drop], [DELETED_TASK_ID], apply=True)
    assert report["account_created"] is False
    assert db.session.scalar(select(db.func.count()).select_from(User)) == 1


def test_plans_that_already_have_an_owner_are_left_alone(legacy):
    """Someone else's rows are not swept up by a claim run later."""
    _app, keep, drop = legacy
    other = User(email="someone.else@example.invalid", password_hash="$argon2id$synthetic")
    db.session.add(other)
    db.session.flush()
    theirs = Plan(
        user_id=other.id, title="다른 계정의 계획",
        start_date=date.fromisoformat(LEGACY_PLAN["start_date"]),
        end_date=date.fromisoformat(LEGACY_PLAN["end_date"]),
        priority="high", success_criterion="합성", estimated_minutes=60,
    )
    db.session.add(theirs)
    db.session.commit()

    claim.run(EMAIL, PASSWORD, [keep], [drop], [DELETED_TASK_ID], apply=True)

    assert db.session.get(Plan, theirs.id).user_id == other.id


def test_the_report_names_ids_and_never_the_diary(legacy):
    """This output goes to a log that gets copied into the submission."""
    _app, keep, drop = legacy
    rendered = claim.render(claim.run(EMAIL, PASSWORD, [keep], [drop], [DELETED_TASK_ID], apply=True))

    assert keep in rendered and drop in rendered and DELETED_TASK_ID in rendered
    assert "NULL=0" in rendered
    for secret in (PASSWORD, EMAIL, LEGACY_PLAN["title"], LEGACY_TASK["content"],
                   LEGACY_PLAN["success_criterion"]):
        assert secret not in rendered


def test_the_report_says_when_not_null_is_still_unsafe(legacy):
    """The NOT NULL migration ships in the *next* deploy, and only if this said so."""
    _app, keep, drop = legacy
    report = claim.run(EMAIL, PASSWORD, [keep], [drop], [DELETED_TASK_ID], apply=True)
    report["unowned_after"] = 1  # as it would read if something were left over
    assert "Do NOT ship the NOT NULL migration" in claim.render(report)


def test_the_not_null_migration_refuses_to_run_before_the_claim(legacy, capfd):
    """Step 10 must not be shippable in the same deploy as step 9.

    `flask db upgrade` runs before BOOT_TASK, so the two together would evaluate
    NOT NULL against rows the claim had not reached yet. The migration counts
    first and names the step that is missing, rather than failing with a
    constraint error that reads like a schema problem.

    Flask-Migrate turns the refusal into a non-zero exit, which is what makes
    `set -e` in deploy/start.sh stop the boot -- so a mis-sequenced deploy fails
    with this sentence in the log instead of starting an app whose data is in an
    unknown state.
    """
    _app, _keep, _drop = legacy
    with pytest.raises(SystemExit) as exit_info:
        upgrade(directory=MIGRATIONS)
    assert exit_info.value.code != 0
    # Alembic reconfigures logging, so the message arrives on the real stderr
    # rather than through pytest's log handler -- which is also where a Render
    # deploy would show it.
    logged = capfd.readouterr().err
    assert "claim_t06_data" in logged
    assert "2 plans still have no owner" in logged


def test_the_not_null_migration_applies_once_the_claim_has_run(legacy):
    app, keep, drop = legacy
    claim.run(EMAIL, PASSWORD, [keep], [drop], [DELETED_TASK_ID], apply=True)
    upgrade(directory=MIGRATIONS)
    columns = {c["name"]: c for c in inspect(db.engine).get_columns("plans")}
    assert columns["user_id"]["nullable"] is False
