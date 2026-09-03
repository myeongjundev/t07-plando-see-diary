"""The T07 matrix must keep saying exactly what the assignment says.

The matrix is the document every other T07 decision is checked against, and the
way it fails is silent: a criterion gets paraphrased while being copied, the
paraphrase is easier to satisfy than the original, and the implementation passes
a test of its own making. So the fixed column is compared character for
character against the assignment, and the set of IDs is compared both ways --
a criterion that quietly goes missing is the same failure as one that drifts.

This runs today, before any of T07 is built. The third test does not: it guards
the planned test names, which do not exist yet, and turns itself on once the
first one does.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ASSIGNMENT = ROOT / "docs" / "source" / "T07-OFFICIAL-ASSIGNMENT.md"
MATRIX = ROOT / "docs" / "T07-ACCEPTANCE-MATRIX.md"

# "- T07-C99 아이디는 맞고 ..." in the assignment's 통과 기준 lists.
CRITERION = re.compile(r"^- (T07-C\d+) (.+)$", re.M)
# "| T07-C99 | 통과 기준 | 확인하는 행동 | 자동 검사 · 증거 |" in the matrix.
ROW = re.compile(r"^\| (T07-C\d+) \| (.+?) \| (.+?) \| (.+?) \|$", re.M)
# Only the criterion tests, named test_c<criterion>_<what>. The matrix also
# mentions the three tests in this file, and counting those as "planned" would
# arm the guard against itself the moment it was written.
TEST_NAME = re.compile(r"`(test_c\d+[a-z0-9_]*)`")
# "**구현 상태: 구현 진행 중**" -- the one line that arms the coverage check.
STATUS_LINE = re.compile(r"^\*\*구현 상태: (.+?)\*\*$", re.M)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def official() -> dict[str, str]:
    return {cid: text.strip() for cid, text in CRITERION.findall(_read(ASSIGNMENT))}


@pytest.fixture(scope="module")
def matrix() -> dict[str, str]:
    return {cid: text.strip() for cid, text, _, _ in ROW.findall(_read(MATRIX))}


def test_matrix_covers_every_official_criterion(official, matrix):
    assert official, "no criteria parsed from the assignment -- the format changed"
    assert sorted(official) == sorted(matrix), {
        "missing_from_matrix": sorted(set(official) - set(matrix)),
        "not_in_assignment": sorted(set(matrix) - set(official)),
    }


def test_matrix_quotes_each_criterion_verbatim(official, matrix):
    drifted = {
        cid: {"assignment": official[cid], "matrix": matrix[cid]}
        for cid in sorted(official)
        if official[cid] != matrix[cid]
    }
    assert not drifted, drifted


def _written_criterion_tests() -> set[str]:
    written: set[str] = set()
    for path in (ROOT / "backend" / "tests").rglob("test_*.py"):
        written |= set(re.findall(r"^def (test_c\d[a-z0-9_]*)", path.read_text(encoding="utf-8"), re.M))
    return written


def test_no_criterion_test_exists_that_the_matrix_does_not_name():
    """A `test_c…` in the suite must be one the matrix asked for.

    This is the direction that matters while the suite is being written. It
    catches the two ways the two documents drift apart day to day: a test
    renamed without updating the matrix, and a test written against a criterion
    the matrix maps somewhere else. The opposite direction -- every promise
    kept -- can only be true at the end, and is checked below.
    """
    planned = set(TEST_NAME.findall(_read(MATRIX)))
    assert planned, "the matrix names no tests -- the format changed"
    orphans = _written_criterion_tests() - planned
    assert not orphans, (
        f"these criterion tests are not in docs/T07-ACCEPTANCE-MATRIX.md: {sorted(orphans)}. "
        "Add the row, or rename the test to the one the matrix already names."
    )


def test_every_test_the_matrix_promises_exists():
    """The full-coverage check, armed by the matrix declaring itself done.

    Demanding all 46 names the moment the first one is written would fail for
    the whole of the implementation, and a test that is red for weeks is a test
    that gets muted. So the matrix's own status line is the switch: while it
    says 구현 진행 중 this reports what is left, and the day it says 구현 완료
    the check becomes binding.

    The switch lives in the document rather than in this file so that the person
    declaring the work finished is the person editing the document that says so.
    """
    text = _read(MATRIX)
    planned = set(TEST_NAME.findall(text))
    missing = sorted(planned - _written_criterion_tests())

    # Anchored to the status line, not to the words appearing anywhere: the
    # paragraph explaining the switch necessarily quotes the value that flips it.
    status = STATUS_LINE.search(text)
    assert status, "the matrix has no 구현 상태 line -- the switch cannot be read"
    if status.group(1).strip() != "구현 완료":
        if missing:
            pytest.skip(f"{len(planned) - len(missing)}/{len(planned)} written; {len(missing)} to go")
        return
    assert not missing, missing
