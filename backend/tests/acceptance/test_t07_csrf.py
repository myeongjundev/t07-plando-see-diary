"""CSRF, three layers deep. Design section 5. Evidence file 06.

No T07-Cxx hangs on this directly -- it belongs to guide item (6) -- but it is
the layer holding up cookie authentication, so it is swept across every
state-changing endpoint rather than demonstrated on one.

The three layers, and what each stops:

    SameSite=Lax       a form on another site cannot send the cookies at all
    JSON content type  a form cannot set the header without a preflight, and
                       no CORS policy answers one
    double submit      only script that can read the __Host- cookie can echo it
"""
from __future__ import annotations


import pytest

from app.auth.cookies import CSRF_COOKIE, CSRF_HEADER
from test_card2_tasks import PLAN, TASK, create_plan, create_task

# Answers for itself: signup and login have no session to bind a token to, and
# refresh is the request that arrives when the access token has expired.
SELF_GUARDED = {"/api/auth/signup", "/api/auth/login", "/api/auth/refresh"}
PUBLIC = {"/api/live", "/api/health"}


@pytest.fixture()
def furnished(client):
    """A signed-in browser with a plan and a task, for endpoints that need ids."""
    plan = create_plan(client)
    task = create_task(client, plan["id"])
    return client, plan, task


def state_changing_rules(app):
    for rule in app.url_map.iter_rules():
        path = str(rule)
        if not path.startswith("/api/") or path in PUBLIC or path in SELF_GUARDED:
            continue
        for method in sorted(rule.methods - {"HEAD", "OPTIONS", "GET"}):
            yield path, method


def concrete(path, plan_id, task_id, reflection_id):
    """Fill route parameters with ids that exist, so a 404 cannot mask a 200."""
    return (path
            .replace("<plan_id>", plan_id)
            .replace("<task_id>", task_id)
            .replace("<reflection_id>", reflection_id))


@pytest.fixture()
def targets(client):
    plan = create_plan(client)
    task = create_task(client, plan["id"])
    reflection = client.post(
        f"/api/plans/{plan['id']}/reflections",
        json={"periodStart": PLAN["startDate"], "periodEnd": PLAN["endDate"], "improvement": "합성 개선"},
    ).get_json()["reflection"]
    return client, plan["id"], task["id"], reflection["id"]


def test_every_state_changing_endpoint_refuses_a_missing_header(app, targets):
    """The sweep, not a sample.

    One endpoint left off the CSRF check is the whole layer gone for whatever
    that endpoint does, and it is not visible by reading -- only by asking every
    one of them.
    """
    client, plan_id, task_id, reflection_id = targets
    checked = 0
    for path, method in state_changing_rules(app):
        url = concrete(path, plan_id, task_id, reflection_id)
        response = client.open(url, method=method, json={}, csrf=False)
        assert response.status_code == 403, f"{method} {url} answered {response.status_code}"
        assert response.get_json()["error"]["message"] == "요청을 확인할 수 없습니다."
        checked += 1
    assert checked >= 8, f"only {checked} state-changing endpoints were swept"


def test_every_state_changing_endpoint_refuses_a_wrong_header(app, targets):
    client, plan_id, task_id, reflection_id = targets
    for path, method in state_changing_rules(app):
        url = concrete(path, plan_id, task_id, reflection_id)
        response = client.open(url, method=method, json={},
                               headers={CSRF_HEADER: "not-the-cookie"}, csrf=False)
        assert response.status_code == 403, f"{method} {url} answered {response.status_code}"


def test_every_state_changing_endpoint_refuses_a_non_json_body(app, targets):
    """415 before anything else: the shape is wrong whoever is asking."""
    client, plan_id, task_id, reflection_id = targets
    for path, method in state_changing_rules(app):
        url = concrete(path, plan_id, task_id, reflection_id)
        response = client.open(url, method=method, data="content=x",
                               content_type="application/x-www-form-urlencoded")
        assert response.status_code == 415, f"{method} {url} answered {response.status_code}"


def test_the_matching_header_is_accepted(furnished):
    """The positive case, so the three above are not passing for the wrong reason."""
    client, plan, task = furnished
    assert client.patch(f"/api/tasks/{task['id']}", json={"content": "합성 수정"}).status_code == 200
    assert client.post(f"/api/plans/{plan['id']}/tasks", json=TASK).status_code == 201


def test_reads_are_not_asked_for_a_token(furnished):
    """GET changes nothing, so requiring a token would only break links."""
    client, plan, task = furnished
    for url in (f"/api/plans/{plan['id']}", f"/api/tasks/{task['id']}", "/api/plans", "/api/export"):
        assert client.get(url).status_code == 200


def test_a_cross_site_form_post_cannot_reach_a_write(app, targets):
    """The shape a real CSRF attempt has: a form, so no custom header at all.

    text/plain is the widest content type a form can send, and it is refused
    before the request touches anything.
    """
    client, plan_id, task_id, _reflection_id = targets
    response = client.post(
        f"/api/tasks/{task_id}/complete",
        data='{"idempotencyKey": "synthetic-forged-001"}',
        content_type="text/plain",
        headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 415
    assert client.get(f"/api/tasks/{task_id}").get_json()["task"]["status"] == "active"
