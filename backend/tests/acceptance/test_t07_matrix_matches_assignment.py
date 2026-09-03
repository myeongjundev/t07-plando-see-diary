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


def test_planned_test_names_exist_once_they_are_written():
    """Every `test_...` the matrix promises must be a real test.

    Skipped while the promises are still all promises: T07 has no tests yet, and
    a failing guard on day one would just get muted. It arms itself as soon as
    one of the named tests appears, so the matrix cannot drift away from the
    suite while the suite is being written.
    """
    planned = set(TEST_NAME.findall(_read(MATRIX)))
    assert planned, "the matrix names no tests -- the format changed"

    written: set[str] = set()
    for path in (ROOT / "backend" / "tests").rglob("test_*.py"):
        written |= set(re.findall(r"^def (test_[a-z0-9_]+)", path.read_text(encoding="utf-8"), re.M))

    if not planned & written:
        pytest.skip(f"none of the {len(planned)} planned T07 tests are written yet")

    assert not planned - written, sorted(planned - written)
