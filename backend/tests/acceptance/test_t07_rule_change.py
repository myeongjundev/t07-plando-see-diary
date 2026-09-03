"""Changing the plan's rule mid-study. T07-C09 through C15.

`changed_at` is the server's clock. A field the client sets is a field the
client can set to whatever makes the ordering look right, and C09 is entirely
about ordering -- so the one number the criteria turn on is the one number the
request cannot supply.

That decides the shape of these tests. A study on fixed 2026-09-01 dates could
never satisfy "the change is before the day-3 record", because the change would
be stamped with today and the day-3 record with a date in the past. So the
fixture builds its five days around the real clock instead, which is also how
the study will actually run.

The anchor is two hours ago in Seoul, and day 2 is the Seoul date that falls on.
Everything else hangs off it, which keeps the two orderings true at every hour
of the day:

  - day 2's record ends at 01:30 on its own date, and that date is only "today"
    when the clock has already passed 02:00, so the record always ends in the
    past
  - day 3 is the day after, which is either tomorrow, or today at a moment when
    the clock has not yet reached 02:00 -- so a record at noon on day 3 is
    always in the future

Every instant is written with an explicit `+09:00`. A record at 00:30+09:00 is
day 2 while the same instant in UTC is day 1, and getting that wrong is exactly
the bug these tests exist to catch.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from test_card2_tasks import PLAN, create_plan, create_task

SEOUL = ZoneInfo("Asia/Seoul")

CHANGE = {
    "reason": "이틀 동안 예상보다 오래 걸려서 하루 분량을 줄인다",
    "ruleBefore": "하루에 할 일 세 개",
    "ruleAfter": "하루에 할 일 두 개",
}


def at(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), tzinfo=SEOUL).isoformat()


def entry(day, start_hour, end_hour, minutes, start_minute=0, end_minute=0):
    return {
        "startedAt": at(day, start_hour, start_minute),
        "endedAt": at(day, end_hour, end_minute),
        "actualMinutes": minutes,
        "blockerReason": "",
    }


def log(client, task_id, payload):
    response = client.post(f"/api/tasks/{task_id}/executions", json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["execution"]


@pytest.fixture()
def study(client):
    """A plan with a day-1 and a day-2 record, ready for the change."""
    day2 = (datetime.now(SEOUL) - timedelta(hours=2)).date()
    day1 = day2 - timedelta(days=1)
    day3 = day2 + timedelta(days=1)

    plan = client.post("/api/plans", json={
        **PLAN,
        "startDate": day1.isoformat(),
        "endDate": (day1 + timedelta(days=6)).isoformat(),
    })
    assert plan.status_code == 201, plan.get_json()
    plan = plan.get_json()["plan"]

    first = create_task(client, plan["id"], content="1일차 할 일",
                        dueDate=day1.isoformat(), estimatedMinutes=60)
    second = create_task(client, plan["id"], content="2일차 할 일",
                         dueDate=day2.isoformat(), estimatedMinutes=60)
    return {
        "plan": plan,
        "day1Date": day1,
        "day2Date": day2,
        "day3Date": day3,
        "day1Task": first,
        "day2Task": second,
        "day1": log(client, first["id"], entry(day1, 10, 11, 60)),
        "day2": log(client, second["id"], entry(day2, 0, 1, 90, end_minute=30)),
        "day3Entry": entry(day3, 12, 13, 40),
    }


def payload(study, **overrides):
    return {
        **CHANGE,
        "day1ExecutionId": study["day1"]["id"],
        "day2ExecutionId": study["day2"]["id"],
        **overrides,
    }


def post(client, study, **overrides):
    return client.post(f"/api/plans/{study['plan']['id']}/rule-changes", json=payload(study, **overrides))


def test_c09_c12_rule_change_sits_between_day2_and_day3(client, study):
    """The record points at day 1 and day 2, and lands between day 2 and day 3.

    Both halves of C09 in one test because they are one property: the change is
    accepted only in the window after day 2 has finished and before day 3 has
    been logged, and the citations name exactly the two records that window is
    defined by.
    """
    created = post(client, study)
    assert created.status_code == 201, created.get_json()
    change = created.get_json()["ruleChange"]

    # C12 -- exactly these two records, named by id, not "two of them".
    assert change["citedExecutionIds"] == {
        "day1": study["day1"]["id"],
        "day2": study["day2"]["id"],
    }

    # C09, first half: after the day-2 record.
    assert change["changedAt"] > study["day2"]["endedAt"]

    # C09, second half: before the day-3 record, which is only written now.
    day3 = log(client, study["day2Task"]["id"], study["day3Entry"])
    assert change["changedAt"] < day3["startedAt"]

    listed = client.get(f"/api/plans/{study['plan']['id']}/rule-changes").get_json()["ruleChanges"]
    assert [row["id"] for row in listed] == [change["id"]]


def test_c10_c11_rule_change_has_time_and_reason(client, study):
    change = post(client, study).get_json()["ruleChange"]
    assert change["changedAt"].endswith("+00:00")  # C10: an instant, with a zone
    assert change["reason"] == CHANGE["reason"]  # C11
    assert change["ruleBefore"] != change["ruleAfter"]


def test_c13_c15_before_after_uses_same_metric_unit_formula(client, study):
    """One metric on both sides of the change, and the arithmetic checks out.

    C13, C14 and C15 are three sentences about the same thing: the comparison
    must not switch metric, unit or formula halfway. The way that is made true
    is that both halves come from one function, so the test's job is to show the
    descriptor is shared and that each side matches 실제분 ÷ 예상분 by hand.
    """
    comparison = post(client, study).get_json()["ruleChange"]["comparison"]

    assert comparison["metric"] == {
        "key": "dailyPlannedVsActual",
        "name": "하루 계획 대비 실제 비율",
        "unit": "배",
        "formula": "실제분 ÷ 예상분",
        "rounding": "소수 둘째 자리 반올림",
        "timezone": "Asia/Seoul",
    }

    before, after = comparison["before"], comparison["after"]
    # The split follows the citations: days 1-2 before, day 3 onward after.
    assert before["dayCount"] == 2 and after["dayCount"] == 5
    assert before["estimatedMinutes"] == 120  # two tasks at 60
    assert before["actualMinutes"] == 150  # 60 + 90
    assert before["ratio"] == 1.25  # 150 / 120, by hand

    # Same formula on the other side, applied to nothing yet.
    assert after["actualMinutes"] == 0
    assert after["ratio"] is None or after["ratio"] == 0.0

    # And the days inside each half carry the same shape as the summary.
    for half in (before, after):
        assert {"dayCount", "estimatedMinutes", "actualMinutes", "ratio", "days"} <= half.keys()


def test_the_two_citations_the_wrong_way_round_are_refused(client, study):
    """C12 says 'exactly', and this is the near miss: both records are real,
    both belong to the study, and they are swapped."""
    response = post(
        client, study,
        day1ExecutionId=study["day2"]["id"],
        day2ExecutionId=study["day1"]["id"],
    )
    assert response.status_code == 400
    assert "1일차" in response.get_json()["error"]["details"]["day1ExecutionId"]


def test_the_same_record_cannot_stand_for_both_days(client, study):
    response = post(client, study, day2ExecutionId=study["day1"]["id"])
    assert response.status_code == 400


def test_a_record_from_another_plan_cannot_be_cited(client, study):
    """Even the user's own record, if it is not this study's."""
    other = create_plan(client)
    other_task = create_task(client, other["id"], content="다른 계획", dueDate=study["day1Date"].isoformat())
    stray = log(client, other_task["id"], entry(study["day1Date"], 10, 11, 60))

    response = post(client, study, day1ExecutionId=stray["id"])
    assert response.status_code == 400
    assert "이 계획" in response.get_json()["error"]["details"]["citations"]


def test_another_accounts_record_cannot_be_cited(client, anonymous_client, study):
    """The citation join is scoped by plan, and plans are scoped by owner.

    Written separately from the plan check above because the failure would look
    identical from outside and mean something much worse: a rule change on my
    study pointing into somebody else's diary.
    """
    anonymous_client.post("/api/auth/signup", json={
        "email": "rule-change-other@example.invalid",
        "password": "합성-다른계정-비밀번호-4a9",
    })
    anonymous_client.post("/api/auth/login", json={
        "email": "rule-change-other@example.invalid",
        "password": "합성-다른계정-비밀번호-4a9",
    })
    their_plan = anonymous_client.post("/api/plans", json=PLAN).get_json()["plan"]
    their_task = anonymous_client.post(
        f"/api/plans/{their_plan['id']}/tasks",
        json={"content": "남의 할 일", "dueDate": study["day1Date"].isoformat(), "priority": "high",
              "tags": [], "estimatedMinutes": 60},
    ).get_json()["task"]
    theirs = log(anonymous_client, their_task["id"], entry(study["day1Date"], 10, 11, 60))

    response = post(client, study, day1ExecutionId=theirs["id"])
    assert response.status_code == 400
    # And the other account's study has nothing on it.
    assert anonymous_client.get(
        f"/api/plans/{their_plan['id']}/rule-changes"
    ).get_json()["ruleChanges"] == []


def test_a_change_after_day_three_is_refused(client, study):
    """The window has closed, and saying so is the only honest answer.

    Accepting it would produce a record whose own timestamp contradicts C09, and
    the alternatives -- backdating it, or reordering the executions -- are worse
    than refusing.
    """
    log(client, study["day2Task"]["id"], study["day3Entry"])

    response = post(client, study)
    assert response.status_code == 400
    assert "3일차" in response.get_json()["error"]["details"]["changedAt"]


def test_an_unchanged_rule_is_not_a_rule_change(client, study):
    response = post(client, study, ruleAfter=CHANGE["ruleBefore"])
    assert response.status_code == 400


@pytest.mark.parametrize("field", ["reason", "ruleBefore", "ruleAfter"])
def test_the_three_texts_are_required(client, study, field):
    assert post(client, study, **{field: "   "}).status_code == 400


def test_the_study_view_numbers_the_days_and_the_records(client, study):
    """What the screen picks the two citations from.

    The day number comes from the server because the boundary is a Seoul day and
    the reviewer's browser may be anywhere. A record's study day must not depend
    on who is looking at it.
    """
    body = client.get(f"/api/plans/{study['plan']['id']}/study").get_json()

    assert body["startDate"] == study["day1Date"].isoformat()
    assert [day["dayNumber"] for day in body["days"]] == [1, 2, 3, 4, 5, 6, 7]
    assert body["days"][0]["ratio"] == 1.0  # 60 planned, 60 actual
    assert body["days"][1]["ratio"] == 1.5  # 60 planned, 90 actual
    assert body["days"][2]["ratio"] is None  # nothing planned: 결측, not zero

    by_id = {row["id"]: row for row in body["executions"]}
    assert by_id[study["day1"]["id"]]["dayNumber"] == 1
    assert by_id[study["day2"]["id"]]["dayNumber"] == 2
    assert by_id[study["day1"]["id"]]["taskContent"] == "1일차 할 일"


def test_another_accounts_study_is_a_404(client, anonymous_client, study):
    assert anonymous_client.get(
        f"/api/plans/{study['plan']['id']}/study"
    ).status_code == 401
    assert client.get("/api/plans/00000000-0000-4000-8000-00000000dead/study").status_code == 404
    assert client.post(
        "/api/plans/00000000-0000-4000-8000-00000000dead/rule-changes", json=payload(study)
    ).status_code == 404


def test_the_observation_plan_refuses_a_day_three_record_before_the_change(
    client, study, monkeypatch
):
    """The other half of C09, enforced from the execution side.

    Without this the five days can be spoilt by logging day 3 before writing the
    change down, and the only ways back are editing a timestamp or starting the
    five days again. The gate applies to the one configured observation plan;
    every other diary stays a diary.
    """
    monkeypatch.setenv("OBSERVATION_PLAN_ID", study["plan"]["id"])

    refused = client.post(
        f"/api/tasks/{study['day2Task']['id']}/executions", json=study["day3Entry"]
    )
    assert refused.status_code == 400
    assert "규칙 변경" in refused.get_json()["error"]["details"]["startedAt"]

    assert post(client, study).status_code == 201

    # And with the change recorded, day 3 goes in.
    assert client.post(
        f"/api/tasks/{study['day2Task']['id']}/executions", json=study["day3Entry"]
    ).status_code == 201


def test_an_ordinary_plan_is_not_subject_to_the_study_order(client, study, monkeypatch):
    """The gate is for the one plan the study is about, and no other.

    The account also holds the T06 diary the claim brought across. Ordering
    somebody's existing records around a criterion they were never part of would
    be a bug that looks like a feature.
    """
    monkeypatch.setenv("OBSERVATION_PLAN_ID", "00000000-0000-4000-8000-00000000feed")
    assert client.post(
        f"/api/tasks/{study['day2Task']['id']}/executions", json=study["day3Entry"]
    ).status_code == 201


def test_no_observation_plan_configured_blocks_nothing(client, study, monkeypatch):
    monkeypatch.delenv("OBSERVATION_PLAN_ID", raising=False)
    assert client.post(
        f"/api/tasks/{study['day2Task']['id']}/executions", json=study["day3Entry"]
    ).status_code == 201
