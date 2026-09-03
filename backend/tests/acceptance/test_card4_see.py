from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.extensions import db
from app.models import Plan, Reflection
from app.services import reflections
from test_card2_tasks import create_plan, create_task, PLAN
from test_card3_executions import LOG


IMPROVEMENT = "작업을 30분 단위로 나눈다"
REFLECTION = {"periodStart": "2026-09-01", "periodEnd": "2026-09-07", "improvement": IMPROVEMENT}
NEXT = {key: value for key, value in {**PLAN, "title": "합성 다음 계획",
        "startDate": "2026-09-08", "endDate": "2026-09-14"}.items() if key != "carriedImprovement"}


def add_log(client, task, minutes, blocker=""):
    response = client.post(f"/api/tasks/{task['id']}/executions", json={**LOG, "actualMinutes": minutes, "blockerReason": blocker})
    assert response.status_code == 201
    return response.json["execution"]


def test_t06_c28_to_c32_and_c83_exact_metrics_and_sources(client, monkeypatch):
    monkeypatch.setattr(reflections, "utc_now", lambda: datetime(2026, 9, 1, 15, tzinfo=timezone.utc))
    plan = create_plan(client)
    tasks = [create_task(client, plan["id"], content=f"합성 집계 {i}", estimatedMinutes=60,
                         dueDate="2026-09-01" if i < 2 else "2026-09-02") for i in range(5)]
    for task in tasks[1:4]:
        assert client.post(f"/api/tasks/{task['id']}/complete", json={"idempotencyKey": "card4-completed"}).status_code == 200
    logs = [add_log(client, tasks[0], 100, "환경 확인"), add_log(client, tasks[0], 60, "두 번째 막힘"),
            add_log(client, tasks[1], 100, "문서 확인")]
    deleted = create_task(client, plan["id"], estimatedMinutes=999)
    add_log(client, deleted, 999, "제외할 기록")
    client.delete(f"/api/tasks/{deleted['id']}", json={})
    other_plan = create_plan(client)
    add_log(client, create_task(client, other_plan["id"]), 999, "다른 계획")

    data = client.get(f"/api/plans/{plan['id']}/see").json
    assert data["today"] == "2026-09-02"
    assert [data[key] for key in ("taskCount", "completedCount", "overdueCount", "blockedTaskCount",
                                  "estimatedMinutes", "actualMinutes", "varianceMinutes")] == [5, 3, 1, 2, 300, 260, -40]
    expected_tasks = {t["id"] for t in tasks}
    expected_logs = {log["id"] for log in logs}
    assert {t["id"] for t in data["records"]["tasks"]} == expected_tasks
    assert {log["id"] for log in data["records"]["executions"]} == expected_logs
    sources = data["sources"]
    assert set(sources["taskCount"]["taskIds"]) == expected_tasks
    assert set(sources["completedCount"]["taskIds"]) == {t["id"] for t in tasks[1:4]}
    assert sources["overdueCount"]["taskIds"] == [tasks[0]["id"]]
    assert set(sources["blockedTaskCount"]["taskIds"]) == {t["id"] for t in tasks[:2]}
    assert set(sources["blockedTaskCount"]["executionIds"]) == expected_logs
    assert set(sources["estimatedMinutes"]["taskIds"]) == expected_tasks
    assert set(sources["actualMinutes"]["executionIds"]) == expected_logs
    assert set(sources["varianceMinutes"]["taskIds"]) == expected_tasks
    assert set(sources["varianceMinutes"]["executionIds"]) == expected_logs
    assert client.get(f"/api/plans/{plan['id']}/see").json == data


def test_empty_aggregates_and_whitespace_blockers(client):
    plan = create_plan(client)
    data = client.get(f"/api/plans/{plan['id']}/see").json
    for metric, source in data["sources"].items():
        assert data[metric] == 0
        assert source == {"taskIds": [], "executionIds": []}
    task = create_task(client, plan["id"], estimatedMinutes=0)
    add_log(client, task, 0, "  \t ")
    assert client.get(f"/api/plans/{plan['id']}/see").json["blockedTaskCount"] == 0


def test_seoul_midnight_overdue_boundary(client, monkeypatch):
    plan = create_plan(client)
    create_task(client, plan["id"], dueDate="2026-09-01")
    monkeypatch.setattr(reflections, "utc_now", lambda: datetime(2026, 9, 1, 14, 59, 59, tzinfo=timezone.utc))
    assert client.get(f"/api/plans/{plan['id']}/see").json["overdueCount"] == 0
    monkeypatch.setattr(reflections, "utc_now", lambda: datetime(2026, 9, 1, 15, tzinfo=timezone.utc))
    assert client.get(f"/api/plans/{plan['id']}/see").json["overdueCount"] == 1


def test_period_selects_due_dates_inclusively_and_all_linked_logs(client):
    plan = create_plan(client)
    tasks = [create_task(client, plan["id"], dueDate=f"2026-09-0{i}", estimatedMinutes=10) for i in range(1, 5)]
    for task in tasks:
        add_log(client, task, 5)
    # Logs were executed September 1; period selects the task cohort by due date.
    response = client.get(f"/api/plans/{plan['id']}/see?periodStart=2026-09-02&periodEnd=2026-09-03")
    data = response.json
    assert data["scope"] == "dueDate"
    assert data["taskCount"] == 2 and data["actualMinutes"] == 10 and data["estimatedMinutes"] == 20
    assert set(data["sources"]["taskCount"]["taskIds"]) == {t["id"] for t in tasks[1:3]}


@pytest.mark.parametrize("query", ["periodStart=2026-09-01", "periodEnd=2026-09-07",
    "periodStart=2026-09-07&periodEnd=2026-09-01", "periodStart=2026-02-30&periodEnd=2026-03-01", "unexpected=1"])
def test_invalid_period_rejected(client, query):
    plan = create_plan(client)
    assert client.get(f"/api/plans/{plan['id']}/see?{query}").status_code == 400


def test_t06_c33_reflection_carries_exact_line_and_retries_reuse_plan(client):
    original = create_plan(client)
    url = f"/api/plans/{original['id']}/reflections"
    saved = client.post(url, json=REFLECTION)
    assert saved.status_code == 201
    row = saved.json["reflection"]
    UUID(row["id"])
    assert row["improvement"] == IMPROVEMENT
    first = client.post(f"/api/reflections/{row['id']}/next-plan", json=NEXT)
    assert first.status_code == 201
    next_plan = first.json["plan"]
    assert next_plan["carriedImprovement"] == IMPROVEMENT
    assert next_plan["id"] != original["id"]
    second = client.post(f"/api/reflections/{row['id']}/next-plan", json=NEXT)
    assert second.status_code == 200 and second.json["replayed"] is True
    assert second.json["plan"] == next_plan
    db.session.remove()
    assert client.get(url).json["reflections"][0]["nextPlanId"] == next_plan["id"]
    assert client.get(f"/api/plans/{next_plan['id']}").json["plan"]["carriedImprovement"] == IMPROVEMENT
    assert client.get(f"/api/plans/{original['id']}").json["plan"] == original
    assert db.session.scalar(select(func.count()).select_from(Plan)) == 2


@pytest.mark.parametrize("change", [{"improvement": " "}, {"improvement": "x" * 501},
    {"improvement": "line1\nline2"}, {"periodEnd": "2026-08-31"}])
def test_invalid_reflection_is_not_saved(client, change):
    plan = create_plan(client)
    assert client.post(f"/api/plans/{plan['id']}/reflections", json={**REFLECTION, **change}).status_code == 400
    assert db.session.scalar(select(func.count()).select_from(Reflection)) == 0


def test_next_plan_rejects_override_and_invalid_dates_without_partial_link(client):
    plan = create_plan(client)
    row = client.post(f"/api/plans/{plan['id']}/reflections", json=REFLECTION).json["reflection"]
    url = f"/api/reflections/{row['id']}/next-plan"
    for payload in ({**NEXT, "carriedImprovement": "tampered"}, {**NEXT, "endDate": "2026-09-01"}):
        assert client.post(url, json=payload).status_code == 400
    assert db.session.get(Reflection, row["id"]).next_plan_id is None
    assert db.session.scalar(select(func.count()).select_from(Plan)) == 1
    assert client.get("/api/plans/missing/see").status_code == 404
    assert client.get("/api/plans/missing/reflections").status_code == 404
    assert client.post("/api/plans/missing/reflections", json=REFLECTION).status_code == 404
    assert client.post("/api/reflections/missing/next-plan", json=NEXT).status_code == 404
