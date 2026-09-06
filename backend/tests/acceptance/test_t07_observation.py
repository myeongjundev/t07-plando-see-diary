"""The five-day observation, checked against what the deployed instance said. T07-C07.

C07 is not a claim about code. It is a claim about one real account -- that the
execution records in it fall on exactly five different Asia/Seoul dates -- and no
local fixture can establish it. So this reads a captured response from the
deployed instance, the same split `test_t07_evidence.py` uses: the thing that
produces evidence is never the thing that judges it.

The file does not exist until the observation ends, and this skips until it does.
A test that asserted five days on day one would be red for the whole study, and a
test that is red for a week is a test that gets muted -- which is the failure
mode `test_t07_matrix_matches_assignment.py` is built around.

Nothing here may be satisfied by writing dates into the file by hand. The JSON is
the deployed instance's own answer, and the protocol's fixed window is asserted
against it, so a record made on the wrong day fails rather than renumbering the
study.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs" / "T07-EVIDENCE"
PROTOCOL = ROOT / "docs" / "T07-STUDY-PROTOCOL.md"

# Outside the `[01][0-9]-*.md` glob that `test_t07_evidence.py` collects, and
# named like `observation-day0.md`: this one is captured from production by hand
# rather than produced by the collector, so the per-file success/denial and
# masking rules written for generated files do not apply to it.
CAPTURE = EVIDENCE / "observation-five-days.md"

# The protocol is frozen. Read the window from it rather than repeating it here,
# so a test cannot quietly disagree with the document it is checking.
PLAN_ID = re.compile(r"관찰 계획 ID \| `([0-9a-f-]{36})`")
DAY_ONE = re.compile(r"1일차 \| \*\*(\d{4}-\d{2}-\d{2})\*\*")

skip_until_observed = pytest.mark.skipif(
    not CAPTURE.exists(),
    reason=(
        "5일 관찰이 끝나면 배포본의 "
        "GET /api/plans/<OBSERVATION_PLAN_ID>/study 응답을 "
        "docs/T07-EVIDENCE/observation-five-days.md 의 ```json 블록에 그대로 붙인다"
    ),
)


def _protocol_window() -> tuple[str, list[str]]:
    """The plan ID and the five dates the frozen protocol fixed."""
    text = PROTOCOL.read_text(encoding="utf-8")
    plan_id = PLAN_ID.search(text)
    day_one = DAY_ONE.search(text)
    assert plan_id, "프로토콜에 관찰 계획 ID가 없다"
    assert day_one, "프로토콜에 1일차 날짜가 없다"

    from datetime import date, timedelta

    start = date.fromisoformat(day_one[1])
    return plan_id[1], [(start + timedelta(days=n)).isoformat() for n in range(5)]


def _captured() -> dict:
    text = CAPTURE.read_text(encoding="utf-8")
    block = re.search(r"```json\n(.*?)\n```", text, re.S)
    assert block, f"{CAPTURE.name} 에 ```json 블록이 없다"
    return json.loads(block[1])


@skip_until_observed
def test_c07_exactly_five_distinct_seoul_dates():
    """Exactly five different Seoul dates carry records, and they are the fixed five.

    Counted from `executionCount`, not from the presence of a row: `/study`
    returns a row for every day in the plan whether or not anything happened on
    it, so counting rows would report the plan's length and call it the study.

    `date` is already the Seoul date -- `metrics.seoul_date()` groups on it, and
    that one function is what the protocol points at for the timezone rule.
    """
    plan_id, window = _protocol_window()
    body = _captured()

    recorded = sorted({day["date"] for day in body["days"] if day["executionCount"] > 0})

    assert recorded == window, (
        f"기록된 Seoul 날짜 {recorded} 가 프로토콜이 고정한 {window} 와 다르다"
    )
    assert len(recorded) == 5

    # The capture has to be of the observation plan. A study response from some
    # other plan could satisfy everything above and mean nothing: C07 is about
    # this account's observation, and C07 in the protocol is scoped to one ID.
    assert plan_id in CAPTURE.read_text(encoding="utf-8"), (
        f"{CAPTURE.name} 에 관찰 계획 ID {plan_id} 가 적혀 있지 않다"
    )
