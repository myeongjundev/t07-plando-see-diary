"""Changing a password, and what that has to kill. T07-C114.

The criterion is one sentence -- "비밀번호를 바꾸거나 로그아웃하면 이전에 발급한 값이
더는 통하지 않는다" -- and almost all of the work is in the last clause. Revoking
rows is easy; making the revocation hold against a refresh already in flight is
what design section 4 spends a lock on, and that is what the concurrency test at
the bottom of this file is for.
"""
from __future__ import annotations

import os

import pytest

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app import create_app
from app.auth.cookies import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE, REFRESH_PATH
from app.extensions import db
from app.models import RefreshSession, SecurityEvent
from app.services.sessions import PASSWORD_CHANGE
from conftest import browser_for, copy_session
from test_t07_signup_login import EMAIL, PASSWORD, login, signup

KEY = "synthetic-test-signing-key-not-a-real-secret-long-enough-for-hs256"
NEW_PASSWORD = "합성-새-비밀번호-8d31"
POSTGRES_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture(autouse=True)
def _fixed_key(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", KEY)


@pytest.fixture()
def client(anonymous_client):
    return anonymous_client


def change(client, current=PASSWORD, new=NEW_PASSWORD, **kwargs):
    headers = kwargs.pop("headers", None)
    if headers is None:
        cookie = client.get_cookie(CSRF_COOKIE)
        headers = {"X-CSRF-Token": cookie.value} if cookie else {}
    return client.post(
        "/api/auth/password",
        json={"currentPassword": current, "newPassword": new},
        headers=headers,
        **kwargs,
    )


def logged_in(client):
    signup(client)
    assert login(client).status_code == 200


def test_the_new_password_works_and_the_old_one_does_not(client):
    logged_in(client)
    assert change(client).status_code == 200

    client.delete_cookie(ACCESS_COOKIE)
    assert login(client, password=PASSWORD).status_code == 401
    assert login(client, password=NEW_PASSWORD).status_code == 200


def test_change_revokes_every_other_session(client, app):
    """Every device, not just this one. That is the whole point of C114.

    Not named `test_c114_…`: the matrix reserves that prefix for the names it
    lists, and C114's own test lives in `test_t07_access_token.py`. This is the
    same property seen from the endpoint rather than the service.
    """
    logged_in(client)
    elsewhere = app.test_client()
    copy_session(client, elsewhere)
    assert elsewhere.get("/api/auth/me").status_code == 200

    assert change(client).status_code == 200

    # The other browser's access token is still signed and still in date, and
    # gets nothing -- the row it names is revoked.
    assert elsewhere.get("/api/auth/me").status_code == 401
    reasons = {row.revoked_reason for row in db.session.scalars(db.select(RefreshSession)) if row.revoked_at}
    assert reasons == {PASSWORD_CHANGE}


def test_the_caller_is_not_logged_out_by_changing_it(client):
    """Logging someone out for changing their password teaches them not to.

    The response carries a new set of cookies, so this session survives while
    every other one dies. Checked on a plain read that needs a live session.
    """
    logged_in(client)
    before = client.get_cookie(REFRESH_COOKIE, path=REFRESH_PATH).value
    assert change(client).status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    assert client.get_cookie(REFRESH_COOKIE, path=REFRESH_PATH).value != before


def test_the_new_session_is_a_new_family(client):
    """A continuation of the old family would be a session the change spared."""
    logged_in(client)
    old_family = db.session.scalar(db.select(RefreshSession)).family_id
    assert change(client).status_code == 200
    live = db.session.scalars(
        db.select(RefreshSession).where(RefreshSession.revoked_at.is_(None))
    ).all()
    assert len(live) == 1
    assert live[0].family_id != old_family


def test_the_current_password_has_to_be_typed_again(client):
    """A session alone must not be enough.

    Otherwise an unattended screen is a full account takeover rather than a
    chance to read someone's diary.
    """
    logged_in(client)
    refused = change(client, current="틀린-비밀번호-1234")
    assert refused.status_code == 401
    # And nothing happened: the old password still works, the session lives.
    assert client.get("/api/auth/me").status_code == 200
    assert db.session.scalar(
        db.select(db.func.count(RefreshSession.id)).where(RefreshSession.revoked_at.is_not(None))
    ) == 0


def test_a_missing_current_password_is_refused(client):
    logged_in(client)
    response = client.post("/api/auth/password", json={"newPassword": NEW_PASSWORD})
    assert response.status_code == 400
    assert "currentPassword" in response.get_json()["error"]["details"]


def test_the_new_password_meets_the_same_policy_as_signup(client):
    """A change form held to a looser rule is a way around the policy."""
    logged_in(client)
    for bad, reason in (
        ("짧다", "비밀번호는 8자 이상이어야 합니다."),
        ("영문도숫자도없는비밀번호", "비밀번호에 영문과 숫자를 함께 넣어 주세요."),
    ):
        response = change(client, new=bad)
        assert response.status_code == 400, bad
        assert response.get_json()["error"]["details"]["newPassword"] == reason
    # Nothing was revoked on the way to being refused.
    assert client.get("/api/auth/me").status_code == 200


def test_changing_it_to_the_same_value_is_refused(client):
    """It would revoke every session and change nothing."""
    logged_in(client)
    response = change(client, new=PASSWORD)
    assert response.status_code == 400
    assert "newPassword" in response.get_json()["error"]["details"]


def test_the_change_needs_the_csrf_header(client):
    """A cross-site change would be an account takeover in one request."""
    logged_in(client)
    # csrf=False is how the shared client is told not to echo the cookie for us.
    assert change(client, headers={}, csrf=False).status_code == 403
    assert login(client, password=PASSWORD).status_code == 200


def test_it_is_refused_without_a_session(anonymous_client):
    response = anonymous_client.post(
        "/api/auth/password",
        json={"currentPassword": PASSWORD, "newPassword": NEW_PASSWORD},
    )
    assert response.status_code == 401


def test_the_audit_trail_records_it_and_carries_no_password(client, app):
    logged_in(client)
    assert change(client).status_code == 200
    events = db.session.scalars(db.select(SecurityEvent)).all()
    assert any(event.event_type == "PASSWORD_CHANGED" for event in events)
    for event in events:
        text = f"{event.detail}"
        assert PASSWORD not in text
        assert NEW_PASSWORD not in text


def test_a_wrong_attempt_is_recorded_as_a_failure(client, app):
    logged_in(client)
    assert change(client, current="틀린-비밀번호-1234").status_code == 401
    assert db.session.scalar(
        db.select(db.func.count(SecurityEvent.id)).where(SecurityEvent.result == "failure")
    ) >= 1
    assert db.session.scalar(
        db.select(db.func.count(SecurityEvent.id)).where(SecurityEvent.event_type == "PASSWORD_CHANGED")
    ) == 0


def test_a_refresh_in_flight_cannot_survive_the_change(tmp_path):
    """The race the lock exists for. Design section 4.

    "Verify token A -- password change revokes everything -- insert successor
    B" leaves B alive: a working session minted from a credential the change was
    meant to kill. The revocation looks correct in the table and is worthless.

    Both operations take the user row first, in that order, which serialises
    them. Whichever runs second sees the world the first one left: either the
    refresh rotates and is then revoked with everything else, or the change
    lands first and the refresh finds nothing live to rotate.

    **What this run proves and what it does not.** SQLite ignores FOR UPDATE and
    serialises writers instead, so it reaches the same outcome by another route
    -- this passes here with the lock removed. It pins the outcome on the engine
    the suite runs on; the variant below runs the same race on the engine that
    is deployed, where the lock is the only thing that can produce it.

    A file-backed database, because SQLite in memory is served from one shared
    connection and two threads on it measure the pool rather than the ordering.
    """
    run_the_race(f"sqlite:///{(tmp_path / 'change.db').as_posix()}")


@pytest.mark.skipif(not POSTGRES_URL, reason="set TEST_DATABASE_URL to check the deployed engine")
def test_a_refresh_in_flight_cannot_survive_the_change_on_postgresql():
    """The same race where FOR UPDATE is real. Run this before shipping step 17."""
    run_the_race(POSTGRES_URL, fresh=True)


def run_the_race(database_url: str, *, fresh: bool = False) -> None:
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": database_url})
    try:
        with app.app_context():
            if fresh:
                db.drop_all()
            db.create_all()
        browser = browser_for(app, email=EMAIL, password=PASSWORD)
        racer = app.test_client()
        copy_session(browser, racer)
        with app.app_context():
            original_family = db.session.scalar(db.select(RefreshSession)).family_id

        barrier = Barrier(2)

        def refresh_now():
            barrier.wait(timeout=10)
            return racer.post(
                "/api/auth/refresh",
                json={},
                headers={"X-CSRF-Token": racer.get_cookie(CSRF_COOKIE).value},
            )

        def change_now():
            barrier.wait(timeout=10)
            return change(browser)

        with ThreadPoolExecutor(max_workers=2) as pool:
            refreshed, changed = [task.result() for task in
                                  [pool.submit(refresh_now), pool.submit(change_now)]]

        assert changed.status_code == 200
        with app.app_context():
            live = db.session.scalars(
                db.select(RefreshSession).where(RefreshSession.revoked_at.is_(None))
            ).all()
            # Exactly one, and it is the session the change itself opened --
            # a new family. Anything of the old family still live would be the
            # successor B this test exists to rule out, whether the refresh won
            # the race or lost it.
            assert len(live) == 1
            assert live[0].family_id != original_family
            assert all(
                row.revoked_at is not None
                for row in db.session.scalars(
                    db.select(RefreshSession).where(RefreshSession.family_id == original_family)
                )
            )

        # And the successor the refresh may have been handed is worth nothing.
        if refreshed.status_code == 200:
            assert racer.get("/api/auth/me").status_code == 401
    finally:
        with app.app_context():
            if fresh:
                db.drop_all()
            db.session.remove()
            db.engine.dispose()
