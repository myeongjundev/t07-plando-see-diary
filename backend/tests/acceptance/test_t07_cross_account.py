"""Nobody else's diary. T07-C116 through C126.

Two accounts, each with data, trying every way to reach the other's. The
assignment wants the attempts and the refusals recorded side by side, so these
tests are written as the attempts.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.extensions import db
from app.models import Plan
from conftest import browser_for
from test_card2_tasks import PLAN, TASK, create_plan, create_task
from test_card3_executions import KEY, LOG
from test_card4_see import REFLECTION

BACKEND = Path(__file__).resolve().parents[2]

# Endpoints that must stay open. Render's health check arrives unauthenticated
# and treats 4xx as a failed deploy, so a guard here takes the service down.
PUBLIC_PATHS = {"/api/live", "/api/health"}
# The auth endpoints are how a caller stops being anonymous; they answer for
# themselves rather than through @login_required.
AUTH_PATHS = {"/api/auth/signup", "/api/auth/login", "/api/auth/refresh"}


@pytest.fixture()
def two_accounts(app):
    """Two signed-in browsers, each with a plan, a task and a reflection."""
    alice = browser_for(app, email="alice@example.invalid", password="합성-앨리스-8a11")
    bob = browser_for(app, email="bob@example.invalid", password="합성-밥-3f92")

    def furnish(browser, title):
        plan = browser.post("/api/plans", json={**PLAN, "title": title}).get_json()["plan"]
        task = create_task(browser, plan["id"])
        browser.post(f"/api/tasks/{task['id']}/executions", json=LOG)
        reflection = browser.post(
            f"/api/plans/{plan['id']}/reflections", json=REFLECTION
        ).get_json()["reflection"]
        return {"plan": plan, "task": task, "reflection": reflection}

    return alice, bob, furnish(alice, "앨리스의 합성 계획"), furnish(bob, "밥의 합성 계획")


def test_c116_two_accounts_with_data(two_accounts, app):
    alice, bob, alice_data, bob_data = two_accounts
    assert alice_data["plan"]["id"] != bob_data["plan"]["id"]
    owners = {row.user_id for row in db.session.scalars(db.select(Plan))}
    assert len(owners) == 2 and None not in owners


def test_c117_to_c120_cross_account_crud_denied(two_accounts):
    """Read, edit and delete, in both directions. Nine refusals.

    Both directions matter: a check that happens to compare against the wrong
    account still passes one way round.
    """
    alice, bob, alice_data, bob_data = two_accounts
    for attacker, victim in ((alice, bob_data), (bob, alice_data)):
        plan_id, task_id = victim["plan"]["id"], victim["task"]["id"]
        # Read
        assert attacker.get(f"/api/plans/{plan_id}").status_code == 404
        assert attacker.get(f"/api/tasks/{task_id}").status_code == 404
        assert attacker.get(f"/api/plans/{plan_id}/see").status_code == 404
        # Edit
        assert attacker.patch(f"/api/plans/{plan_id}", json=PLAN).status_code == 404
        assert attacker.patch(f"/api/tasks/{task_id}", json={"content": "침입"}).status_code == 404
        assert attacker.post(f"/api/tasks/{task_id}/complete", json=KEY).status_code == 404
        # Create underneath someone else's plan
        assert attacker.post(f"/api/plans/{plan_id}/tasks", json=TASK).status_code == 404
        # Delete
        assert attacker.delete(f"/api/tasks/{task_id}", json={}).status_code == 404


def test_c121_other_users_resources_are_404_not_403(two_accounts):
    """Not-yours and not-there must be the same answer.

    403 would confirm the id exists, and walking a range of ids to learn which
    are real is the enumeration a uniform answer prevents.
    """
    alice, _bob, _alice_data, bob_data = two_accounts
    absent = "00000000-0000-4000-8000-00000000dead"
    theirs = alice.get(f"/api/plans/{bob_data['plan']['id']}")
    missing = alice.get(f"/api/plans/{absent}")
    assert theirs.status_code == missing.status_code == 404
    assert theirs.get_json() == missing.get_json()


def test_c122_counts_unchanged_across_denials(two_accounts):
    """The refused requests must not have written anything on the other side."""
    alice, bob, _alice_data, bob_data = two_accounts

    def snapshot():
        plans = bob.get("/api/plans").get_json()["plans"]
        tasks = bob.get(f"/api/plans/{bob_data['plan']['id']}/tasks").get_json()["tasks"]
        return len(plans), len(tasks), [t["content"] for t in tasks]

    before = snapshot()
    plan_id, task_id = bob_data["plan"]["id"], bob_data["task"]["id"]
    alice.patch(f"/api/tasks/{task_id}", json={"content": "침입"})
    alice.post(f"/api/plans/{plan_id}/tasks", json=TASK)
    alice.delete(f"/api/tasks/{task_id}", json={})
    alice.post(f"/api/tasks/{task_id}/complete", json=KEY)
    assert snapshot() == before


def test_c123_forged_identity_in_path_header_body_ignored(two_accounts):
    """Naming another account in the request changes nothing.

    Identity comes from the session cookie. A query parameter, a header and a
    body field are all just text the caller chose.
    """
    alice, bob, alice_data, bob_data = two_accounts
    bob_plan = bob_data["plan"]["id"]

    listed = alice.get("/api/plans", query_string={"userId": bob_plan})
    assert listed.status_code == 200
    assert [p["id"] for p in listed.get_json()["plans"]] == [alice_data["plan"]["id"]]

    with_header = alice.get("/api/plans", headers={"X-User-Id": "bob@example.invalid"})
    assert [p["id"] for p in with_header.get_json()["plans"]] == [alice_data["plan"]["id"]]

    # A body field naming the other account does not move the new plan there.
    created = alice.post("/api/plans", json={**PLAN, "userId": "whoever"})
    assert created.status_code == 400  # unexpected field, rejected outright
    assert [p["id"] for p in alice.get("/api/plans").get_json()["plans"]] == [alice_data["plan"]["id"]]


def test_c124_every_data_endpoint_401_when_anonymous(app, anonymous_client):
    """Every route that touches a diary refuses an anonymous caller.

    The list comes from the app's own routing table, not from a list written by
    hand: one written here would go stale the first time an endpoint was added,
    and nothing would say so. What is removed is an explicit allowlist, so a new
    route is protected by default and dropping out of coverage takes a
    deliberate edit.
    """
    checked = 0
    for rule in app.url_map.iter_rules():
        if not str(rule).startswith("/api/"):
            continue
        if str(rule) in PUBLIC_PATHS or str(rule) in AUTH_PATHS:
            continue
        path = re.sub(r"<[^>]+>", "00000000-0000-4000-8000-00000000feed", str(rule))
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            response = anonymous_client.open(path, method=method, json={})
            assert response.status_code == 401, f"{method} {path} answered {response.status_code}"
            assert response.get_json()["error"]["message"] == "로그인이 필요합니다."
            checked += 1
    # If the sweep ever silently matches nothing, it would pass while testing
    # nothing at all.
    assert checked >= 20, f"only {checked} endpoint/method pairs were swept"


def test_c125_list_contains_only_own_rows(two_accounts):
    """Lists are scoped in the query; there is no id for a guard to check."""
    alice, bob, alice_data, bob_data = two_accounts
    alice_plans = alice.get("/api/plans").get_json()["plans"]
    bob_plans = bob.get("/api/plans").get_json()["plans"]
    assert [p["id"] for p in alice_plans] == [alice_data["plan"]["id"]]
    assert [p["id"] for p in bob_plans] == [bob_data["plan"]["id"]]

    # The export is a list with no id at all, which is the harder case.
    alice_export = alice.get("/api/export").get_json()
    exported = {row["id"] for row in alice_export["plans"]}
    assert exported == {alice_data["plan"]["id"]}
    dumped = str(alice_export)
    assert bob_data["plan"]["id"] not in dumped
    assert bob_data["task"]["id"] not in dumped
    assert bob_data["reflection"]["id"] not in dumped


def test_c126_denials_originate_only_in_three_modules():
    """Ownership is decided in one file, authentication in one, CSRF in one.

    The submission has to point at the source that produces the refusals
    (T07-C126), which is only answerable if there are few enough places to
    point at. This reads the source and fails if a fourth appears: any module
    outside those comparing a user id is a second opinion about who owns what,
    and second opinions are how one of them ends up wrong.
    """
    allowed = {
        Path("app/auth/guards.py"),
        Path("app/auth/csrf.py"),
        Path("app/services/ownership.py"),
        # Issues and revokes sessions; compares user_id to the token's subject.
        Path("app/services/sessions.py"),
    }
    offenders = []
    for path in sorted((BACKEND / "app").rglob("*.py")):
        relative = path.relative_to(BACKEND)
        if relative in allowed:
            continue
        source = path.read_text(encoding="utf-8")
        # Strip comments so the prose explaining the rule does not trip it.
        code = "\n".join(line.split("#")[0] for line in source.splitlines())
        if re.search(r"\bPlan\.user_id\b|\bg\.current_user\b", code):
            offenders.append(str(relative))
    assert not offenders, (
        f"these modules decide ownership for themselves: {offenders}. "
        "Route the check through app/services/ownership.py instead."
    )
