"""Deleting an account, and taking its diary with it. T07-C133, C134.

Most of what makes this work is in the foreign keys, and
`test_t07_ownership_cascade.py` already asserts their delete actions from the
metadata. What is left for here is the endpoint: that it re-authenticates, that
the rows really are gone afterwards, that it takes nobody else's, and that the
audit trail keeps the event while losing the name.
"""
from __future__ import annotations

import pytest

from app.extensions import db
from app.models import (
    ExecutionLog,
    Plan,
    Reflection,
    RefreshSession,
    SecurityEvent,
    Task,
    User,
)
from conftest import browser_for
from test_card2_tasks import PLAN, create_task
from test_card3_executions import LOG
from test_card4_see import REFLECTION

ALICE = ("alice@example.invalid", "합성-앨리스-8a11")
BOB = ("bob@example.invalid", "합성-밥-3f92")

# What one furnished account leaves behind. CompletionEvent is not here: it is
# written when a task is completed, and the fixture only logs work against one.
OWNED_MODELS = (Plan, Task, ExecutionLog, Reflection)


def furnish(browser, title):
    """One plan with a task, an execution log and a reflection under it."""
    plan = browser.post("/api/plans", json={**PLAN, "title": title}).get_json()["plan"]
    task = create_task(browser, plan["id"])
    browser.post(f"/api/tasks/{task['id']}/executions", json=LOG)
    browser.post(f"/api/plans/{plan['id']}/reflections", json=REFLECTION)
    return plan


@pytest.fixture()
def accounts(app):
    """Two furnished accounts. Bob is the control: nothing of his may move."""
    alice = browser_for(app, email=ALICE[0], password=ALICE[1])
    bob = browser_for(app, email=BOB[0], password=BOB[1])
    return alice, bob, furnish(alice, "앨리스의 합성 계획"), furnish(bob, "밥의 합성 계획")


def delete_account(browser, password=ALICE[1], **kwargs):
    return browser.delete("/api/account", json={"password": password}, **kwargs)


def count(model, **where):
    statement = db.select(db.func.count()).select_from(model)
    for column, value in where.items():
        statement = statement.where(getattr(model, column) == value)
    return db.session.scalar(statement)


def test_c134_account_delete_removes_own_data(accounts):
    """The account goes, and so does everything written under it."""
    alice, _bob, _alice_plan, _bob_plan = accounts
    for model in OWNED_MODELS:
        assert count(model) >= 1

    assert delete_account(alice).status_code == 200

    assert db.session.scalar(
        db.select(db.func.count()).select_from(User).where(User.email == ALICE[0])
    ) == 0
    # One account's worth of each remains -- Bob's. Nothing of Alice's does.
    for model in OWNED_MODELS:
        assert count(model) >= 1
    assert count(Plan, title="앨리스의 합성 계획") == 0


def test_the_other_account_is_untouched(accounts):
    """A delete that reached one row too far would be unrecoverable.

    The two accounts are furnished identically, so each model holds exactly two
    rows before and must hold exactly one after -- a cascade that followed the
    wrong key would show up as a zero here rather than as a missing row nobody
    counted.
    """
    alice, bob, _alice_plan, bob_plan = accounts
    for model in OWNED_MODELS:
        assert count(model) == 2, model

    assert delete_account(alice).status_code == 200

    assert bob.get("/api/auth/me").status_code == 200
    assert bob.get(f"/api/plans/{bob_plan['id']}").status_code == 200
    for model in OWNED_MODELS:
        assert count(model) == 1, model
    assert count(Plan, title="밥의 합성 계획") == 1


def test_the_sessions_go_with_the_account(accounts):
    """A live session naming a deleted user would be a row nothing owns."""
    alice, _bob, _a, _b = accounts
    assert delete_account(alice).status_code == 200
    assert alice.get("/api/auth/me").status_code == 401
    # Bob still has his; Alice's rows are gone rather than orphaned.
    remaining = db.session.scalars(db.select(RefreshSession)).all()
    assert remaining
    assert all(db.session.get(User, row.user_id) is not None for row in remaining)


def test_the_password_has_to_be_typed_again(accounts):
    """The one action here that cannot be undone. A found screen is not enough."""
    alice, _bob, alice_plan, _b = accounts
    refused = delete_account(alice, password="틀린-비밀번호-1234")
    assert refused.status_code == 401
    assert alice.get("/api/auth/me").status_code == 200
    assert alice.get(f"/api/plans/{alice_plan['id']}").status_code == 200


def test_a_missing_password_is_refused(accounts):
    alice, _bob, _a, _b = accounts
    response = alice.delete("/api/account", json={})
    assert response.status_code == 400
    assert "password" in response.get_json()["error"]["details"]
    assert alice.get("/api/auth/me").status_code == 200


def test_it_needs_the_csrf_header(accounts):
    """A cross-site delete would be the worst possible one-request attack."""
    alice, _bob, _a, _b = accounts
    assert delete_account(alice, headers={}, csrf=False).status_code == 403
    assert alice.get("/api/auth/me").status_code == 200


def test_it_is_refused_without_a_session(anonymous_client):
    response = anonymous_client.delete("/api/account", json={"password": ALICE[1]})
    assert response.status_code == 401


def test_the_audit_trail_keeps_the_event_and_loses_the_name(accounts):
    """C134 wants the data gone; a breach investigation wants the record.

    `security_events.user_id` is SET NULL rather than CASCADE, so the row
    survives the delete with the column that named the person emptied. Both at
    once is the whole reason for that one exception among the cascades.
    """
    alice, _bob, _a, _b = accounts
    assert delete_account(alice).status_code == 200

    deletions = db.session.scalars(
        db.select(SecurityEvent).where(SecurityEvent.event_type == "ACCOUNT_DELETED")
    ).all()
    assert len(deletions) == 1
    assert deletions[0].user_id is None
    # And nothing anywhere in the trail still names the account.
    for event in db.session.scalars(db.select(SecurityEvent)):
        assert ALICE[0] not in f"{event.detail}"
        assert ALICE[1] not in f"{event.detail}"


def test_c133_export_is_one_file_and_only_mine(accounts):
    """One request, one file, and nothing of the other account in it."""
    alice, _bob, alice_plan, bob_plan = accounts
    response = alice.get("/api/export")
    assert response.status_code == 200
    assert response.headers["Content-Disposition"] == 'attachment; filename="t06-diary-v2.json"'

    body = response.get_data(as_text=True)
    assert alice_plan["id"] in body
    assert bob_plan["id"] not in body
    assert "밥의 합성 계획" not in body
    # A file, not a page of a list: everything the account has is in this one
    # response, so there is nothing to ask for next.
    payload = response.get_json()
    assert payload["plans"] and len(payload["plans"]) == 1


def test_export_after_delete_is_refused(accounts):
    """The account is gone; so is the way to read what it had."""
    alice, _bob, _a, _b = accounts
    assert delete_account(alice).status_code == 200
    assert alice.get("/api/export").status_code == 401
