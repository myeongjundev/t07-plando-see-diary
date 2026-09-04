"""Deleting an account must take its data with it (T07-C134).

Two checks, because they fail in different places.

The first reads the mapped schema and needs no database at all. PostgreSQL
defaults a foreign key with no delete action to NO ACTION, so one such key
anywhere on the path from `users` down does not weaken the cascade -- it aborts
it, and the delete fails partway. That is the bug the design review found in
`reflections`, and it is invisible on SQLite, which does not enforce foreign keys
unless asked. Reading the metadata catches it on every run, on any engine.

The second actually deletes a user, and only runs where the engine that will be
deployed is available. `TEST_DATABASE_URL` opts in; without it the test skips
rather than passing on SQLite and claiming something it did not check.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from flask_migrate import upgrade
from sqlalchemy import inspect, select, text

from app import create_app
from app.extensions import db
from app.models import Plan, Reflection, Task, User
from conftest import postgres_url_or_skip, refuse_production

POSTGRES_URL = postgres_url_or_skip(os.getenv("TEST_DATABASE_URL"))


def postgres_app():
    """An app on the PostgreSQL target, once it is confirmed safe to wipe.

    These tests drop every table. `refuse_production` is what stands between
    that and a connection string copied off the Neon dashboard.
    """
    refuse_production(POSTGRES_URL)
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": POSTGRES_URL})

# Foreign keys that must carry an explicit delete action for the account-delete
# cascade to reach the bottom. Value is the action the design calls for.
REQUIRED_ACTIONS = {
    ("plans", "user_id"): "CASCADE",
    ("refresh_sessions", "user_id"): "CASCADE",
    ("security_events", "user_id"): "SET NULL",
    ("tasks", "plan_id"): "CASCADE",
    ("plan_revisions", "plan_id"): "CASCADE",
    ("reflections", "plan_id"): "CASCADE",
    ("reflections", "next_plan_id"): "SET NULL",
    ("plan_rule_changes", "plan_id"): "CASCADE",
    ("plan_rule_change_citations", "rule_change_id"): "CASCADE",
    # NO ACTION, deliberately, and the one entry here that is not a cascade.
    # RESTRICT would refuse a standalone delete of a cited execution -- which is
    # wanted -- but it is checked the instant the row goes, and an account
    # delete cascades to executions and to citations down two separate paths
    # with no order between them. NO ACTION refuses the same standalone delete
    # and is checked at the end of the statement, by which point the citation
    # has gone too.
    ("plan_rule_change_citations", "execution_id"): "NO ACTION",
}


def test_every_ownership_foreign_key_declares_a_delete_action():
    for (table_name, column), expected in REQUIRED_ACTIONS.items():
        table = db.metadata.tables[table_name]
        matching = [fk for fk in table.foreign_keys if fk.parent.name == column]
        assert matching, f"{table_name}.{column} has no foreign key"
        for fk in matching:
            assert fk.ondelete == expected, (
                f"{table_name}.{column} is ondelete={fk.ondelete!r}, expected {expected!r}. "
                "Without it PostgreSQL aborts the users -> plans delete instead of following it."
            )


@pytest.mark.skipif(not POSTGRES_URL, reason="set TEST_DATABASE_URL to check the deployed engine")
def test_deleting_a_user_removes_their_data_on_postgresql():
    app = postgres_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        try:
            user = User(email="cascade@example.invalid", password_hash="not-a-real-hash")
            db.session.add(user)
            db.session.flush()

            plan = Plan(
                user_id=user.id, title="합성", start_date="2026-09-01", end_date="2026-09-07",
                priority="high", success_criterion="합성", estimated_minutes=60,
            )
            successor = Plan(
                user_id=user.id, title="합성 다음", start_date="2026-09-08", end_date="2026-09-14",
                priority="low", success_criterion="합성", estimated_minutes=60,
            )
            db.session.add_all([plan, successor])
            db.session.flush()
            db.session.add(Task(
                plan_id=plan.id, content="합성", due_date="2026-09-02",
                priority="high", estimated_minutes=30,
            ))
            db.session.add(Reflection(
                plan_id=plan.id, period_start="2026-09-01", period_end="2026-09-07",
                improvement="합성", next_plan_id=successor.id,
            ))
            db.session.commit()

            db.session.delete(user)
            db.session.commit()

            # Nothing of the account survives, and the delete reached every level
            # rather than stopping at the first key without an action.
            for model in (User, Plan, Task, Reflection):
                assert db.session.scalars(select(model)).all() == []
        finally:
            db.session.remove()
            db.drop_all()
            db.engine.dispose()


@pytest.mark.skipif(not POSTGRES_URL, reason="set TEST_DATABASE_URL to check the deployed engine")
def test_next_plan_link_is_cleared_rather_than_deleting_the_reflection():
    """A successor plan going away must not take the reflection with it.

    `reflections.next_plan_id` is only a pointer forward. CASCADE there would
    delete a reflection because the plan it suggested was removed, which loses
    a record the user wrote.
    """
    app = postgres_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        try:
            owner = User(email="pointer@example.invalid", password_hash="not-a-real-hash")
            db.session.add(owner)
            db.session.flush()
            kept = Plan(
                user_id=owner.id, title="유지", start_date="2026-09-01", end_date="2026-09-07",
                priority="high", success_criterion="합성", estimated_minutes=60,
            )
            dropped = Plan(
                user_id=owner.id, title="삭제 대상", start_date="2026-09-08", end_date="2026-09-14",
                priority="low", success_criterion="합성", estimated_minutes=60,
            )
            db.session.add_all([kept, dropped])
            db.session.flush()
            reflection = Reflection(
                plan_id=kept.id, period_start="2026-09-01", period_end="2026-09-07",
                improvement="합성", next_plan_id=dropped.id,
            )
            db.session.add(reflection)
            db.session.commit()

            db.session.execute(text("DELETE FROM plans WHERE id = :id"), {"id": dropped.id})
            db.session.commit()
            db.session.expire_all()

            survivor = db.session.get(Reflection, reflection.id)
            assert survivor is not None
            assert survivor.next_plan_id is None
        finally:
            db.session.remove()
            db.drop_all()
            db.engine.dispose()


def test_new_auth_tables_are_present_in_the_mapped_schema():
    """Step 1 is not done until all four exist under the names the design uses."""
    assert {"users", "refresh_sessions", "login_attempts", "security_events"} <= set(db.metadata.tables)


def test_plans_user_id_is_required():
    """A plan with no owner is unrepresentable, not merely unusual.

    It arrived nullable and was tightened once claim_t06_data had given the T06
    rows an owner. The two could not ship together: `deploy/start.sh` runs
    `flask db upgrade` before BOOT_TASK, so the NOT NULL would have been
    evaluated before the claim it depends on.
    """
    assert db.metadata.tables["plans"].columns["user_id"].nullable is False


def test_migration_head_builds_the_same_tables_and_columns_as_the_models(tmp_path):
    """The models and the migrations must describe the same database.

    Every other test builds its schema with `db.create_all()`, straight from the
    models, so a column added to a model and forgotten in a migration passes the
    whole suite and then fails on the deployed instance as a missing column.
    This is the only test that runs the migrations and compares the result.
    """
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'head.db').as_posix()}",
    })
    migrations = str(Path(__file__).resolve().parents[2] / "migrations")
    try:
        with app.app_context():
            upgrade(directory=migrations)
            inspector = inspect(db.engine)
            built = set(inspector.get_table_names()) - {"alembic_version"}
            assert built == set(db.metadata.tables)
            for name, table in db.metadata.tables.items():
                assert {c["name"] for c in inspector.get_columns(name)} == set(table.columns.keys()), name
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
