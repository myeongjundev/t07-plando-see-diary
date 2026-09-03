from uuid import UUID


PLAN = {
    "title": "합성 계획",
    "startDate": "2026-09-01",
    "endDate": "2026-09-07",
    "priority": "high",
    "successCriterion": "카드 2 검사 통과",
    "estimatedMinutes": 300,
    "carriedImprovement": None,
}

TASK = {
    "content": "Flask 할 일 API 구현",
    "dueDate": "2026-09-03",
    "priority": "high",
    "tags": ["backend", "test"],
    "estimatedMinutes": 90,
}


def create_plan(client):
    response = client.post("/api/plans", json=PLAN)
    assert response.status_code == 201
    return response.get_json()["plan"]


def create_task(client, plan_id, **overrides):
    payload = {**TASK, **overrides}
    response = client.post(f"/api/plans/{plan_id}/tasks", json=payload)
    assert response.status_code == 201
    return response.get_json()["task"]


def test_t06_c09_and_c14_to_c17_create_task_fields(client):
    plan = create_plan(client)
    task = create_task(client, plan["id"])

    UUID(task["id"])
    assert task["planId"] == plan["id"]  # T06-C09
    assert task["dueDate"] == "2026-09-03"  # T06-C14
    assert task["priority"] == "high"  # T06-C15
    assert task["tags"] == ["backend", "test"]  # T06-C16
    assert task["estimatedMinutes"] == 90  # T06-C17
    assert task["durationUnit"] == "minutes"  # T06-C17


def test_t06_c10_to_c13_edit_complete_reopen_and_delete(client):
    plan = create_plan(client)
    task = create_task(client, plan["id"])
    other = create_task(client, plan["id"], content="남아 있어야 하는 할 일", dueDate="2026-09-04")

    edited = client.patch(
        f"/api/tasks/{task['id']}",
        json={"content": "Flask 할 일 API와 검사 구현"},
    )
    assert edited.status_code == 200
    assert edited.get_json()["task"]["id"] == task["id"]
    assert edited.get_json()["task"]["content"] == "Flask 할 일 API와 검사 구현"  # T06-C10

    completed = client.post(f"/api/tasks/{task['id']}/complete", json={"idempotencyKey": "card2-complete"})
    assert completed.get_json()["task"]["status"] == "completed"  # T06-C11

    reopened = client.post(f"/api/tasks/{task['id']}/reopen", json={})
    assert reopened.get_json()["task"]["status"] == "active"  # T06-C12

    deleted = client.delete(f"/api/tasks/{task['id']}", json={})
    assert deleted.status_code == 204
    assert client.get(f"/api/tasks/{task['id']}").status_code == 404  # T06-C13
    remaining_ids = [item["id"] for item in client.get(f"/api/plans/{plan['id']}/tasks").get_json()["tasks"]]
    assert remaining_ids == [other["id"]]


def test_t06_c18_search_and_c19_combined_filters(client):
    plan = create_plan(client)
    matching = create_task(client, plan["id"], content="고유검색어 배포 검사", priority="high")
    create_task(client, plan["id"], content="문서 정리", priority="low", tags=["docs"])
    client.post(f"/api/tasks/{matching['id']}/complete", json={"idempotencyKey": "card2-filter"})

    searched = client.get(f"/api/plans/{plan['id']}/tasks?q=고유검색어")
    assert [task["id"] for task in searched.get_json()["tasks"]] == [matching["id"]]  # T06-C18

    filtered = client.get(f"/api/plans/{plan['id']}/tasks?status=completed&priority=high")
    tasks = filtered.get_json()["tasks"]
    assert [task["id"] for task in tasks] == [matching["id"]]  # T06-C19
    assert all(task["status"] == "completed" and task["priority"] == "high" for task in tasks)


def test_t06_c20_sort_is_declared_and_deterministic(client):
    plan = create_plan(client)
    low = create_task(client, plan["id"], content="낮은 우선순위", priority="low", dueDate="2026-09-01")
    high_later = create_task(client, plan["id"], content="높음 늦은 마감", priority="high", dueDate="2026-09-04")
    high_earlier = create_task(client, plan["id"], content="높음 빠른 마감", priority="high", dueDate="2026-09-02")

    first = client.get(f"/api/plans/{plan['id']}/tasks").get_json()
    second = client.get(f"/api/plans/{plan['id']}/tasks").get_json()
    expected_ids = [high_earlier["id"], high_later["id"], low["id"]]
    assert [task["id"] for task in first["tasks"]] == expected_ids
    assert [task["id"] for task in second["tasks"]] == expected_ids
    assert first["sort"] == "priority → dueDate → createdAt → id"

