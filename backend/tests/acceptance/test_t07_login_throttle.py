"""Brute-force throttling on the login path. Design section 6.

No T07 criterion names this, so nothing here is a `test_c…`: the matrix guard
reserves that prefix for the fixed list. It is here because C99's promise --
that a wrong password and an unregistered address are indistinguishable --
survives online guessing only if guessing is slow, and because a counter that
forgets everything when Render Free wakes the instance would be the appearance
of a throttle rather than one.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models import LoginAttempt
from app.services import throttle

EMAIL = "throttle-user@example.invalid"
PASSWORD = "합성-비밀번호-3d81"
WRONG = "틀린-비밀번호-0000"


@pytest.fixture()
def client(anonymous_client):
    """Signed out: these tests are about the door, not about the diary."""
    return anonymous_client


def signup(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/auth/signup", json={"email": email, "password": password})


def login(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def fail_times(client, count, email=EMAIL):
    """`count` wrong passwords, asserting each is still a plain refusal."""
    for _ in range(count):
        assert login(client, email=email, password=WRONG).status_code == 401


def rewind(seconds, *, email=None):
    """Move recorded attempts back in time, to age a window without sleeping."""
    query = db.select(LoginAttempt)
    if email is not None:
        query = query.where(LoginAttempt.email_normalized == email)
    for row in db.session.scalars(query):
        row.attempted_at = throttle._aware(row.attempted_at) - timedelta(seconds=seconds)
    db.session.commit()


def test_the_sixth_wrong_password_is_refused_with_429(client):
    signup(client)
    fail_times(client, throttle.EMAIL_IP_THRESHOLD)

    blocked = login(client, password=WRONG)
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "60"
    assert blocked.get_json()["error"]["message"] == "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요."


def test_the_lock_holds_even_against_the_right_password(client):
    """A lock an attacker can step past by guessing correctly is not a lock."""
    signup(client)
    fail_times(client, throttle.EMAIL_IP_THRESHOLD)
    assert login(client).status_code == 429


def test_an_unknown_address_locks_exactly_like_a_real_one(client):
    """Otherwise "this address never locks" is the enumeration C99 closes."""
    signup(client)
    fail_times(client, throttle.EMAIL_IP_THRESHOLD, email="absent@example.invalid")

    absent = login(client, email="absent@example.invalid", password=WRONG)
    assert absent.status_code == 429
    assert absent.headers["Retry-After"] == "60"

    # And the two refusals are the same response, body included.
    fail_times(client, throttle.EMAIL_IP_THRESHOLD)
    present = login(client, password=WRONG)
    assert present.status_code == absent.status_code
    assert present.get_json() == absent.get_json()


def test_requests_made_while_locked_do_not_extend_the_lock(client):
    """The lock must not be an attack: `blocked` rows are not counted."""
    signup(client)
    fail_times(client, throttle.EMAIL_IP_THRESHOLD)
    for _ in range(10):
        assert login(client, password=WRONG).status_code == 429

    counted = db.session.scalars(
        db.select(LoginAttempt).where(LoginAttempt.result == throttle.FAILURE)
    ).all()
    assert len(counted) == throttle.EMAIL_IP_THRESHOLD
    # The refusals are still recorded, just under a result the counter ignores.
    assert db.session.scalar(
        db.select(db.func.count(LoginAttempt.id)).where(LoginAttempt.result == throttle.BLOCKED)
    ) == 10

    # So the lock ends when the first one said it would, not ten requests later.
    rewind(61)
    assert login(client, password=WRONG).status_code == 401


def test_each_failure_after_a_lock_doubles_the_next_one(client):
    """A fixed sixty seconds is a rate an attacker simply accepts."""
    signup(client)
    fail_times(client, throttle.EMAIL_IP_THRESHOLD)
    assert login(client, password=WRONG).headers["Retry-After"] == "60"

    rewind(61)
    assert login(client, password=WRONG).status_code == 401  # the sixth failure
    assert login(client, password=WRONG).headers["Retry-After"] == "120"

    rewind(121)
    assert login(client, password=WRONG).status_code == 401  # the seventh
    assert login(client, password=WRONG).headers["Retry-After"] == "240"


def test_the_ladder_doubles_and_then_stops_at_the_ceiling():
    """A legitimate user who is being targeted must not be locked out for good.

    Checked on the function rather than through the endpoint. Reaching the
    ceiling by real requests means serving out 60 + 120 + 240 + 480 seconds of
    locks, by which point the first failures have aged out of the fifteen-minute
    window -- so the ladder's top is a property of the arithmetic and the
    endpoint cannot demonstrate it without a fake clock.
    """
    now = throttle.utc_now()
    ladder = [
        throttle._lock_for(throttle.EMAIL_IP_THRESHOLD + step, throttle.EMAIL_IP_THRESHOLD, now) - now
        for step in range(throttle.MAX_STEP + 4)
    ]
    assert ladder[:4] == [
        timedelta(seconds=60),
        timedelta(seconds=120),
        timedelta(seconds=240),
        timedelta(seconds=480),
    ]
    assert all(step == throttle.MAX_LOCK for step in ladder[4:])
    # Below the threshold there is no lock at all.
    assert throttle._lock_for(throttle.EMAIL_IP_THRESHOLD - 1, throttle.EMAIL_IP_THRESHOLD, now) is None


def test_a_successful_login_clears_that_pairs_failures(client):
    signup(client)
    fail_times(client, throttle.EMAIL_IP_THRESHOLD - 1)
    assert login(client).status_code == 200

    assert db.session.scalar(
        db.select(db.func.count(LoginAttempt.id)).where(
            LoginAttempt.email_normalized == EMAIL,
            LoginAttempt.result == throttle.FAILURE,
        )
    ) == 0
    # And the count really did restart, rather than the rows merely being gone.
    fail_times(client, throttle.EMAIL_IP_THRESHOLD - 1)
    assert login(client, password=WRONG).status_code == 401


def test_a_successful_login_does_not_clear_the_address_wide_count(client):
    """Otherwise one account of the attacker's own resets the global limit."""
    signup(client)
    for index in range(throttle.IP_THRESHOLD - 1):
        login(client, email=f"sweep-{index}@example.invalid", password=WRONG)
    assert login(client).status_code == 200

    # The twentieth failure from this address still reaches the wide threshold.
    assert login(client, email="sweep-last@example.invalid", password=WRONG).status_code == 401
    assert login(client, email="another@example.invalid", password=WRONG).status_code == 429


def test_the_address_wide_count_locks_an_address_that_never_failed(client):
    """Spreading guesses over many addresses is the shape the pair count misses."""
    signup(client)
    for index in range(throttle.IP_THRESHOLD):
        login(client, email=f"spread-{index}@example.invalid", password=WRONG)
    assert login(client).status_code == 429


def test_failures_outside_the_window_stop_counting(client):
    signup(client)
    fail_times(client, throttle.EMAIL_IP_THRESHOLD - 1)
    rewind(throttle.WINDOW.total_seconds() + 1)
    fail_times(client, throttle.EMAIL_IP_THRESHOLD - 1)
    assert login(client).status_code == 200


def test_a_malformed_body_is_counted_and_answered_like_any_other_failure(client):
    """A body that never parsed must not be the cheap, unlimited probe."""
    signup(client)
    for _ in range(throttle.IP_THRESHOLD):
        probe = client.post("/api/auth/login", json={"email": "not-an-address", "password": "x"})
        assert probe.status_code == 401
    assert login(client).status_code == 429


def test_nothing_secret_reaches_the_attempts_table(client):
    signup(client)
    fail_times(client, 2)
    rows = db.session.scalars(db.select(LoginAttempt)).all()
    assert rows
    for row in rows:
        assert PASSWORD not in (row.email_normalized or "")
        assert WRONG not in (row.email_normalized or "")
        # HMAC-SHA-256 hex, never the address itself.
        assert row.ip_hash != "127.0.0.1"
        assert len(row.ip_hash) == 64


def test_pruning_drops_rows_past_the_retention_window(client):
    signup(client)
    fail_times(client, 2)
    rewind(throttle.RETENTION.total_seconds() + 60)
    throttle.prune()
    assert db.session.scalar(db.select(db.func.count(LoginAttempt.id))) == 0


def test_the_count_survives_the_process_restarting(tmp_path, monkeypatch):
    """Render Free wakes as a new process. An in-memory counter would be empty.

    A file-backed database and a second `create_app`, because that is what a
    restart is -- and a fixed IP_HASH_SECRET, because a per-process key would
    make the same client a stranger to the new process even with the rows
    still there.
    """
    monkeypatch.setenv("IP_HASH_SECRET", "합성-테스트-키-only-for-tests")
    uri = f"sqlite:///{(tmp_path / 'throttle.db').as_posix()}"

    first = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": uri})
    with first.app_context():
        db.create_all()
        browser = first.test_client()
        assert signup(browser).status_code == 201
        fail_times(browser, throttle.EMAIL_IP_THRESHOLD)
        db.session.remove()
        db.engine.dispose()

    second = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": uri})
    with second.app_context():
        try:
            assert login(second.test_client(), password=WRONG).status_code == 429
        finally:
            db.session.remove()
            db.engine.dispose()
