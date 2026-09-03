"""Attaching the T06 rows to an account. T07-C100.

This is the one script that edits real diary data on the deployed database, and
it runs once, unattended, during a boot nobody is watching. So the tests are
mostly about what it refuses to do.
"""
from __future__ import annotations

import importlib.util
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import Plan, Task, User
from legacy_rows import LEGACY_PLAN, LEGACY_TASK, seed_legacy_plan_and_task

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "claim_t06_data.py"
_spec = importlib.util.spec_from_file_location("claim_t06_data", SCRIPT)
claim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(claim)

EMAIL = "owner@example.invalid"
PASSWORD = "합성-이관-비밀번호-6b2e"
OTHER_PLAN_ID = "00000000-0000-4000-8000-000000000a02"


@pytest.fixture()
def legacy(app):
    """Two unowned plans: one to keep, one that stands for the demo leftovers."""
    seed_legacy_plan_and_task()
    db.session.add(Plan(
        id=OTHER_PLAN_ID, title="합성 데모 계획",
        start_date=date.fromisoformat(LEGACY_PLAN["start_date"]),
        end_date=date.fromisoformat(LEGACY_PLAN["end_date"]),
        priority="low", success_criterion="합성", estimated_minutes=10,
    ))
    db.session.commit()
    return LEGACY_PLAN["id"], OTHER_PLAN_ID


def test_c100_claim_leaves_no_orphan_plan(legacy):
    keep, drop = legacy
    report = claim.run(EMAIL, PASSWORD, [keep], [drop], apply=True)

    assert report["unowned_after"] == 0
    owner = db.session.scalar(select(User).where(User.email == EMAIL))
    assert owner is not None
    assert db.session.get(Plan, keep).user_id == owner.id
    # The excluded plan is gone, and took its children with it.
    assert db.session.get(Plan, drop) is None
    assert db.session.get(Task, LEGACY_TASK["id"]) is not None


def test_a_plan_in_neither_list_stops_the_run(legacy):
    """The point of the lists is that a person decided. An unlisted plan means
    nobody did, and guessing at it is how real data gets deleted."""
    keep, _drop = legacy
    with pytest.raises(claim.ClaimRefused, match=OTHER_PLAN_ID):
        claim.run(EMAIL, PASSWORD, [keep], [], apply=True)
    # Refused before anything moved.
    assert db.session.get(Plan, keep).user_id is None
    assert db.session.scalar(select(db.func.count()).select_from(User)) == 0


def test_an_id_in_both_lists_stops_the_run(legacy):
    keep, drop = legacy
    with pytest.raises(claim.ClaimRefused, match="both lists"):
        claim.run(EMAIL, PASSWORD, [keep, drop], [drop], apply=True)
    assert db.session.get(Plan, keep).user_id is None


def test_a_soft_deleted_synthetic_task_can_be_excluded_by_fixed_id(legacy):
    keep, drop = legacy
    task = db.session.get(Task, LEGACY_TASK["id"])
    task.deleted_at = datetime.now(timezone.utc)
    db.session.commit()

    report = claim.run(EMAIL, PASSWORD, [keep], [drop], [task.id], apply=True)

    assert report["delete_task_ids"] == [LEGACY_TASK["id"]]
    assert db.session.get(Task, LEGACY_TASK["id"]) is None
    assert db.session.get(Plan, keep) is not None


def test_an_active_task_can_never_be_excluded(legacy):
    keep, drop = legacy
    with pytest.raises(claim.ClaimRefused, match="active task"):
        claim.run(EMAIL, PASSWORD, [keep], [drop], [LEGACY_TASK["id"]], apply=True)

    assert db.session.get(Task, LEGACY_TASK["id"]) is not None
    assert db.session.get(Plan, keep).user_id is None
    assert db.session.scalar(select(db.func.count()).select_from(User)) == 0


def test_without_apply_nothing_changes(legacy):
    """A deploy that runs this by accident must be a no-op."""
    keep, drop = legacy
    report = claim.run(EMAIL, PASSWORD, [keep], [drop], apply=False)

    assert report["to_claim"] == 1 and report["to_delete"] == 1
    assert report["unowned_after"] == 2
    assert db.session.get(Plan, keep).user_id is None
    assert db.session.get(Plan, drop) is not None
    assert db.session.scalar(select(db.func.count()).select_from(User)) == 0


def test_running_twice_is_the_same_as_running_once(legacy):
    """A deploy can be retried -- by Render, or by someone pushing again."""
    keep, drop = legacy
    first = claim.run(EMAIL, PASSWORD, [keep], [drop], apply=True)
    second = claim.run(EMAIL, PASSWORD, [keep], [drop], apply=True)

    assert first["account_created"] is True
    assert second["account_created"] is False
    assert second["to_claim"] == 0 and second["to_delete"] == 0
    assert second["unowned_after"] == 0
    assert db.session.scalar(select(db.func.count()).select_from(User)) == 1
    assert db.session.scalar(select(db.func.count()).select_from(Plan)) == 1


def test_an_existing_account_is_reused_not_duplicated(legacy):
    keep, drop = legacy
    db.session.add(User(email=EMAIL, password_hash="$argon2id$synthetic"))
    db.session.commit()
    report = claim.run(EMAIL, PASSWORD, [keep], [drop], apply=True)
    assert report["account_created"] is False
    assert db.session.scalar(select(db.func.count()).select_from(User)) == 1


def test_plans_that_already_have_an_owner_are_left_alone(legacy, client):
    """Someone else's rows are not swept up by a claim run later."""
    keep, drop = legacy
    theirs = client.post("/api/plans", json={
        "title": "다른 계정의 계획", "startDate": "2026-09-01", "endDate": "2026-09-07",
        "priority": "high", "successCriterion": "합성", "estimatedMinutes": 60,
        "carriedImprovement": None,
    }).get_json()["plan"]
    before = db.session.get(Plan, theirs["id"]).user_id

    claim.run(EMAIL, PASSWORD, [keep], [drop], apply=True)

    assert db.session.get(Plan, theirs["id"]).user_id == before


def test_the_report_names_ids_and_never_the_diary(legacy):
    """This output goes to a log that gets copied into the submission."""
    keep, drop = legacy
    text = claim.render(claim.run(EMAIL, PASSWORD, [keep], [drop], apply=True))

    assert keep in text and drop in text
    assert "NULL=0" in text
    for secret in (PASSWORD, EMAIL, LEGACY_PLAN["title"], LEGACY_TASK["content"],
                   LEGACY_PLAN["success_criterion"]):
        assert secret not in text


def test_the_report_says_when_not_null_is_still_unsafe(legacy, monkeypatch):
    """The NOT NULL migration ships in the *next* deploy, and only if this said so."""
    keep, drop = legacy
    report = claim.run(EMAIL, PASSWORD, [keep], [drop], apply=True)
    report["unowned_after"] = 1  # as it would read if something were left over
    assert "Do NOT ship the NOT NULL migration" in claim.render(report)
