"""The parts of the hashing benchmark that only run on the deployed instance.

The benchmark itself is far too slow to run in the suite, and its interesting
measurements only exist on Render's tenth of a core. But two pieces of it decide
what those measurements mean, and both are pure functions: the percentile that
picks the budget verdict, and the /proc reader that produces every memory number
in the table.

The /proc reader never executes on the machine this is written on. A mistake in
it does not fail loudly -- it returns None, the memory columns fill with dashes,
and the cost is another deploy to find out why.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

BENCH_PATH = Path(__file__).resolve().parents[2] / "scripts" / "bench_password_hashing.py"
_spec = importlib.util.spec_from_file_location("bench_password_hashing", BENCH_PATH)
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)


# A real /proc/self/status prologue, trimmed. VmRSS is not the first VM line and
# VmHWM sits right before it, so a reader that matched too loosely would take
# the high-water mark instead of the current value.
PROC_STATUS_SAMPLE = """\
Name:\tpython3
State:\tR (running)
VmPeak:\t  310124 kB
VmSize:\t  309100 kB
VmHWM:\t   84532 kB
VmRSS:\t   72180 kB
RssAnon:\t   60112 kB
Threads:\t2
"""


def test_reads_current_rss_not_the_high_water_mark(tmp_path):
    status = tmp_path / "status"
    status.write_text(PROC_STATUS_SAMPLE, encoding="ascii")
    assert bench.read_rss_kib(str(status)) == 72180


def test_missing_proc_file_reports_nothing_rather_than_crashing(tmp_path):
    # Windows and macOS have no /proc. The benchmark must still produce its
    # timing table there and simply decline to make a memory claim.
    assert bench.read_rss_kib(str(tmp_path / "absent")) is None


def test_unparsable_status_reports_nothing(tmp_path):
    status = tmp_path / "status"
    status.write_text("VmRSS:\tnot-a-number\n", encoding="ascii")
    assert bench.read_rss_kib(str(status)) is None


@pytest.mark.parametrize(
    "values, fraction, expected",
    [
        ([10.0], 0.95, 10.0),
        ([1.0, 2.0, 3.0, 4.0], 0.50, 2.0),
        # Nearest-rank p95 of twenty samples is the twentieth: the worst one.
        # This is the property the budget verdict rests on -- the tail has to be
        # a number that actually happened, not an average of the top two.
        ([float(n) for n in range(1, 21)], 0.95, 19.0),
        ([float(n) for n in range(1, 21)], 1.0, 20.0),
        ([], 0.95, 0.0),
    ],
)
def test_percentile_returns_an_observed_value(values, fraction, expected):
    assert bench.percentile(values, fraction) == expected


def test_percentile_never_reads_past_the_end():
    """A tiny sample must not index off the end of the list.

    Three repeats is a realistic setting on a tenth of a core, and p95 of three
    samples rounds up to the third.
    """
    assert bench.percentile([5.0, 7.0, 9.0], 0.95) == 9.0
