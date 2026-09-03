"""The observation metric, on its own. T07-C05, C06, C08, C23 to C26.

The rule-change tests check that the before/after comparison uses one metric.
These check the metric itself, because the study protocol fixes the arithmetic
on day 1 and cannot change it for five days -- so the arithmetic is worth
pinning where it can be read in one screen, rather than only through an
endpoint.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.services import metrics


@pytest.mark.parametrize(
    "estimated, actual, expected",
    [
        (120, 150, 1.25),
        (60, 60, 1.0),
        (60, 0, 0.0),
        # 실제분 ÷ 예상분 to two places, rounded half **up**. Python's built-in
        # round() gives 1.12 here, because it rounds halves to even; a reader
        # checking 225/200 by hand gets 1.13, and a metric that disagrees with
        # hand arithmetic on the boundary is one nobody can check.
        (200, 225, 1.13),
        (200, 275, 1.38),
        (3, 1, 0.33),
        (3, 2, 0.67),
    ],
)
def test_c26_rounds_to_two_decimals(estimated, actual, expected):
    assert metrics.ratio(estimated, actual) == expected


@pytest.mark.parametrize("estimated", [0, -5])
def test_c23_missing_value_rule(estimated):
    """C23's missing-data rule, and the reason it is `None` and not zero.

    A day nobody planned anything for did not go 0x to plan; it has no ratio at
    all. Returning 0.0 would put an invented point in the middle of a five-day
    comparison and drag the summary down with it.
    """
    assert metrics.ratio(estimated, 90) is None


def test_the_day_boundary_is_seoul_not_the_readers_clock():
    """An instant just after midnight in Seoul belongs to the Seoul day.

    The same instant is the previous day in UTC. Every day number in the study
    turns on this, so it is asserted directly rather than inferred from a
    response.
    """
    just_after_midnight = datetime(2026, 9, 1, 15, 30, tzinfo=timezone.utc)
    assert just_after_midnight.date().isoformat() == "2026-09-01"
    assert metrics.seoul_date(just_after_midnight).isoformat() == "2026-09-02"

    # And a naive timestamp -- which is what SQLite hands back -- is read as
    # UTC, not as whatever zone the machine running this happens to be in.
    assert metrics.seoul_date(datetime(2026, 9, 1, 15, 30)).isoformat() == "2026-09-02"

    aware_seoul = datetime(2026, 9, 2, 0, 30, tzinfo=ZoneInfo("Asia/Seoul"))
    assert metrics.seoul_date(aware_seoul).isoformat() == "2026-09-02"


def test_a_summary_divides_the_totals_rather_than_averaging_the_days():
    """C15: one calculation rule, at the day level and at the summary level.

    Averaging the daily ratios would give a different number and would weight a
    ten-minute day the same as a six-hour one. Summing the minutes and dividing
    once is the same formula applied to a bigger bucket.
    """
    days = [
        {"estimatedMinutes": 60, "actualMinutes": 30, "ratio": 0.5},
        {"estimatedMinutes": 600, "actualMinutes": 900, "ratio": 1.5},
    ]
    summary = metrics.summarize(days)

    assert summary["estimatedMinutes"] == 660
    assert summary["actualMinutes"] == 930
    assert summary["ratio"] == metrics.ratio(660, 930) == 1.41
    # Not the average of the daily ratios, which would be 1.0.
    assert summary["ratio"] != 1.0


def test_a_summary_says_how_many_days_had_no_ratio():
    """Days without a ratio must not silently vanish into the total."""
    summary = metrics.summarize([
        {"estimatedMinutes": 0, "actualMinutes": 20, "ratio": None},
        {"estimatedMinutes": 60, "actualMinutes": 60, "ratio": 1.0},
    ])
    assert summary["dayCount"] == 2
    assert summary["daysWithoutRatio"] == 1
    # The minutes from the unrated day are still counted -- they happened.
    assert summary["actualMinutes"] == 80


def test_the_descriptor_is_the_protocol_written_down():
    """What ships with every comparison, so C13-C15 are readable off the wire."""
    assert metrics.descriptor() == {
        "key": "dailyPlannedVsActual",
        "name": "하루 계획 대비 실제 비율",
        "unit": "배",
        "formula": "실제분 ÷ 예상분",
        "rounding": "소수 둘째 자리 반올림",
        "timezone": "Asia/Seoul",
    }


# ---------------------------------------------------------------------------
# The three rules that are about the data, not the arithmetic. They go through
# the API, because "nothing is dropped" is a claim about the pipeline from the
# execution record to the number on the screen, and a pure function cannot drop
# a row it was never handed.
# ---------------------------------------------------------------------------

from datetime import date, time, timedelta  # noqa: E402

from test_card2_tasks import PLAN, create_task  # noqa: E402

SEOUL = ZoneInfo("Asia/Seoul")
START = date(2026, 9, 1)


def _instant(day_offset: int, hour: int) -> str:
    moment = datetime.combine(START + timedelta(days=day_offset), time(hour), tzinfo=SEOUL)
    return moment.isoformat()


def _entry(day_offset: int, hour: int, minutes: int) -> dict:
    return {
        "startedAt": _instant(day_offset, hour),
        "endedAt": _instant(day_offset, hour + 1),
        "actualMinutes": minutes,
        "blockerReason": "",
    }


def _plan_with_days(client, days: list[tuple[int, int, list[int]]]):
    """A plan whose day N has `planned` minutes and one record per `actual`."""
    plan = client.post("/api/plans", json={
        **PLAN, "startDate": START.isoformat(),
        "endDate": (START + timedelta(days=6)).isoformat(),
    }).get_json()["plan"]
    for offset, planned, actuals in days:
        task = create_task(
            client, plan["id"], content=f"{offset + 1}일차",
            dueDate=(START + timedelta(days=offset)).isoformat(), estimatedMinutes=planned,
        )
        for index, minutes in enumerate(actuals):
            assert client.post(
                f"/api/tasks/{task['id']}/executions", json=_entry(offset, 9 + index, minutes)
            ).status_code == 201
    return plan


def test_c24_duplicate_value_rule(client):
    """Two records on one day are two records. Nothing is merged.

    An execution record carries a start, an end and a blocker reason, so two of
    them mean two sittings, not one value written twice. De-duplicating would
    silently delete work the user did. The count is reported so a day that looks
    doubled can be checked rather than guessed at.
    """
    plan = _plan_with_days(client, [(0, 120, [40, 50])])
    day = client.get(f"/api/plans/{plan['id']}/study").get_json()["days"][0]

    assert day["executionCount"] == 2
    assert day["actualMinutes"] == 90  # 40 + 50, both kept
    assert day["ratio"] == metrics.ratio(120, 90) == 0.75


def test_c25_outlier_rule(client):
    """A day far outside the others is kept, and moves the total.

    Five days is too short for an outlier rule to be anything but a way to
    delete an inconvenient day -- dropping one of five discards a fifth of the
    study. So the check is that the extreme day is still there and still counted.
    """
    plan = _plan_with_days(client, [(0, 60, [60]), (1, 60, [600])])
    body = client.get(f"/api/plans/{plan['id']}/study").get_json()

    assert body["days"][1]["ratio"] == 10.0  # kept, not clipped
    assert body["days"][1]["actualMinutes"] == 600


def test_c08_same_formula_across_five_days(client):
    """One calculation rule over all five days, checked against hand arithmetic.

    Not "the code agrees with itself": each day's number is recomputed here from
    the two minute totals the same response reports, which is the sum a reviewer
    would do by hand (T07-C132 asks for exactly that comparison).
    """
    plan = _plan_with_days(client, [
        (0, 60, [60]),
        (1, 60, [90]),
        (2, 120, [45]),
        (3, 90, [90]),
        (4, 30, [20, 25]),
    ])
    body = client.get(f"/api/plans/{plan['id']}/study").get_json()
    five = body["days"][:5]

    assert [day["ratio"] for day in five] == [1.0, 1.5, 0.38, 1.0, 1.5]
    for day in five:
        assert day["ratio"] == metrics.ratio(day["estimatedMinutes"], day["actualMinutes"])

    # And the same formula one level up: minutes summed, divided once.
    assert metrics.summarize(five)["ratio"] == metrics.ratio(360, 330) == 0.92
