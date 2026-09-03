from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import create_app
from conftest import browser_for, copy_session
from app.extensions import db
from app.models import CompletionEvent, ExecutionLog
from test_card2_tasks import create_plan, create_task


LOG = {"startedAt": "2026-09-01T13:00:00+09:00", "endedAt": "2026-09-01T14:30:00+09:00",
       "actualMinutes": 75, "blockerReason": "배포 환경 변수 확인"}
KEY = {"idempotencyKey": "synthetic-completion-001"}


def test_t06_c23_to_c27_persist_log_without_changing_estimates(client):
    plan = create_plan(client)
    task = create_task(client, plan["id"])
    response = client.post(f"/api/tasks/{task['id']}/executions", json=LOG)
    assert response.status_code == 201
    log = response.json["execution"]
    UUID(log["id"])
    assert log["taskId"] == task["id"]
    for field in ("startedAt", "endedAt"):
        assert datetime.fromisoformat(log[field]) == datetime.fromisoformat(LOG[field])
        assert log[field].endswith("+00:00")
    assert log["actualMinutes"] == 75
    assert log["durationUnit"] == "minutes"
    assert log["blockerReason"] == "배포 환경 변수 확인"
    db.session.remove()
    assert client.get(f"/api/tasks/{task['id']}/executions").json["executions"] == [log]
    assert client.get(f"/api/tasks/{task['id']}").json["task"] == task
    assert client.get(f"/api/plans/{plan['id']}").json["plan"] == plan


def test_t06_c21_c22_duplicate_completion_and_see_count(client):
    plan = create_plan(client)
    task = create_task(client, plan["id"])
    see_url = f"/api/plans/{plan['id']}/see"
    before = client.get(see_url).json["completedCount"]
    url = f"/api/tasks/{task['id']}/complete"
    first, second = client.post(url, json=KEY), client.post(url, json=KEY)
    assert first.status_code == second.status_code == 200
    assert first.json["completionEvent"] == second.json["completionEvent"]
    assert first.json["replayed"] is False and second.json["replayed"] is True
    assert db.session.scalar(select(func.count()).select_from(CompletionEvent)) == 1
    events = client.get(f"/api/tasks/{task['id']}/completions").json["completionEvents"]
    assert events == [first.json["completionEvent"]]
    assert client.get(see_url).json["completedCount"] == before + 1
    assert client.get(see_url).json["completedTaskIds"] == [task["id"]]


def test_replay_after_reopen_and_new_completion_cycle(client):
    plan = create_plan(client)
    task = create_task(client, plan["id"])
    url = f"/api/tasks/{task['id']}"
    first = client.post(url + "/complete", json=KEY).json
    assert client.post(url + "/complete", json={"idempotencyKey": "another-key"}).status_code == 409
    client.post(url + "/reopen", json={})
    replay = client.post(url + "/complete", json=KEY).json
    assert replay["completionEvent"] == first["completionEvent"]
    assert replay["task"]["status"] == "active"
    assert client.get(f"/api/plans/{plan['id']}/see").json["completedCount"] == 0
    assert client.post(url + "/complete", json={"idempotencyKey": "another-key"}).status_code == 200
    assert db.session.scalar(select(func.count()).select_from(CompletionEvent)) == 2
    assert client.get(f"/api/plans/{plan['id']}/see").json["completedCount"] == 1
    client.delete(url, json={})
    assert client.get(f"/api/plans/{plan['id']}/see").json["completedCount"] == 0
    assert client.post(url + "/complete", json=KEY).status_code == 404
    assert client.post(url + "/executions", json=LOG).status_code == 404
    assert client.get(url + "/executions").status_code == 404


def test_database_rejects_duplicate_completion_key(client):
    plan = create_plan(client)
    task = create_task(client, plan["id"])
    client.post(f"/api/tasks/{task['id']}/complete", json=KEY)
    db.session.add(CompletionEvent(task_id=task["id"], idempotency_key=KEY["idempotencyKey"]))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    assert db.session.scalar(select(func.count()).select_from(CompletionEvent)) == 1


@pytest.mark.parametrize("patch", [
    {"startedAt": "2026-09-01T13:00:00"}, {"startedAt": 42},
    {"endedAt": LOG["startedAt"]}, {"endedAt": "2026-09-01T12:00:00+09:00"},
    {"endedAt": "invalid"}, {"actualMinutes": True}, {"actualMinutes": -1},
    {"actualMinutes": 1.5}, {"actualMinutes": 1000001}, {"blockerReason": None},
    {"blockerReason": "x" * 501}, {"unexpected": "field"},
])
def test_invalid_log_is_atomic(client, patch):
    plan = create_plan(client)
    task = create_task(client, plan["id"])
    response = client.post(f"/api/tasks/{task['id']}/executions", json={**LOG, **patch})
    assert response.status_code == 400
    assert db.session.scalar(select(func.count()).select_from(ExecutionLog)) == 0
    assert client.get(f"/api/tasks/{task['id']}").json["task"] == task


# `None` means no body at all, which T07 refuses one step earlier: every
# state-changing request must declare application/json, so it never reaches the
# payload check. Still refused, still nothing written -- which is what this test
# is for -- but with the status that says why.
@pytest.mark.parametrize("payload, expected", [(None, 415), ({}, 400), ([], 400),
                                               ({"idempotencyKey": "short"}, 400),
                                               ({"idempotencyKey": 42}, 400),
                                               ({"idempotencyKey": "x" * 101}, 400)])
def test_invalid_completion_does_not_mutate(client, payload, expected):
    plan = create_plan(client)
    task = create_task(client, plan["id"])
    assert client.post(f"/api/tasks/{task['id']}/complete", json=payload).status_code == expected
    assert db.session.scalar(select(func.count()).select_from(CompletionEvent)) == 0
    assert client.get(f"/api/tasks/{task['id']}").json["task"] == task


def test_concurrent_duplicate_requests(tmp_path):
    # Independent sessions/connections on a real file, not a shared in-memory connection.
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'race.db').as_posix()}"})
    with app.app_context():
        db.create_all()
    client = browser_for(app)
    plan = create_plan(client)
    task = create_task(client, plan["id"])
    barrier = Barrier(4)

    def complete(_):
        with app.test_client() as worker:
            copy_session(client, worker)
            barrier.wait(timeout=10)
            return worker.post(f"/api/tasks/{task['id']}/complete", json=KEY)

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(complete, range(4)))
        assert [r.status_code for r in responses] == [200] * 4
        assert len({r.json["completionEvent"]["id"] for r in responses}) == 1
        assert sum(not r.json["replayed"] for r in responses) == 1
        assert client.get(f"/api/plans/{plan['id']}/see").json["completedCount"] == 1
        with app.app_context():
            assert db.session.scalar(select(func.count()).select_from(CompletionEvent)) == 1
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
